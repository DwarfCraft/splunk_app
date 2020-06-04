"""
(C) 2020 Splunk Inc. All rights reserved.

Module for Drone Mode Subscription Requests
"""
import sys
import os
import base64
import json
from functools import partial
from datetime import datetime
from copy import deepcopy
from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'lib']))
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
from google.protobuf.json_format import MessageToDict
from twisted.internet import defer
from twisted.python.failure import Failure
from twisted.web import http
from cloudgateway.private.encryption.encryption_handler import encrypt_for_send, sign_detached
from cloudgateway.private.sodium_client import SodiumClient
from cloudgateway.splunk.encryption import SplunkEncryptionContext
from splapp_protocol import drone_mode_pb2
from spacebridgeapp.util import constants
from spacebridgeapp.util.py23 import b64encode_to_str, b64_to_urlsafe_b64
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.util.guid_generator import get_guid
from spacebridgeapp.util.error_utils import check_and_raise_error
from spacebridgeapp.util.kvstore import build_containedin_clause
from spacebridgeapp.util.time_utils import get_current_timestamp_str
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.messages.request_context import RequestContext
from spacebridgeapp.drone_mode.data.drone_mode_data import TVConfig, TVList
from spacebridgeapp.drone_mode.data.enums import TVEventType, IPadEventType
from spacebridgeapp.data.subscription_data import Subscription, SubscriptionCredential, DroneModeTVEvent, DroneModeiPadEvent
from spacebridgeapp.request.request_processor import SpacebridgeAuthHeader
from spacebridgeapp.rest.devices.user_devices import public_keys_for_device
from spacebridgeapp.drone_mode.drone_mode_subscription_update_message import build_drone_mode_subscription_update
from spacebridgeapp.subscriptions.subscription_update_message import build_send_subscription_update_request
from spacebridgeapp.drone_mode.drone_mode_utils import get_drone_mode_tvs, get_registered_tvs, has_grid
from spacebridgeapp.request.request_processor import get_splunk_cookie, JWTAuthHeader


LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_drone_mode_subscription_requests.log",
                       "drone_mode_subscription_requests")

@defer.inlineCallbacks
def fetch_valid_tvs(request_context, async_kvstore_client, user=None, tv_ids=None):
    """
    Function to fetch valid tvs for drone mode
    :param request_context: request context used to make kvstore requests
    :param async_kvstore_client: async client used to make kvstore requests
    :param device_id: optional device id to filter on
    """
    # fetch list of all registered tvs
    valid_tv_protos = []
    valid_tv_json = []
    if not user:
        user = request_context.current_user
    tv_list = yield get_registered_tvs(request_context.system_auth_header,
                                       user,
                                       async_kvstore_client,
                                       device_ids=tv_ids)
    # fetch devices from drone_mode_tvs collection
    # if there is data, return that, otherwise just return blank TV data
    # construct set containing device ids
    drone_mode_tvs = yield get_drone_mode_tvs(request_context, async_kvstore_client, user=user)
    LOGGER.debug('registered_tvs=%s, drone mode tvs=%s', tv_list, drone_mode_tvs)
    drone_mode_tv_dict = {}
    for element in drone_mode_tvs:
        if constants.CONTENT in element:
            raw_id = base64.urlsafe_b64decode(str(element[constants.KEY]))
            encoded_id = b64encode_to_str(raw_id)
            element[constants.DEVICE_ID] = encoded_id
            drone_mode_tv_dict[encoded_id] = element

    if tv_list:
        active_subscriptions = yield fetch_subscriptions(request_context.auth_header,
                                                         async_kvstore_client,
                                                         user_list=[user],
                                                         subscription_type=constants.DRONE_MODE_TV,
                                                         device_ids=tv_ids)


        LOGGER.debug('active_subscriptions=%s', active_subscriptions)

        active_subscription_ids = {subscription.device_id for subscription in active_subscriptions}
        for device in tv_list:
            device_id = device[constants.DEVICE_ID]
            tv_proto = drone_mode_pb2.TVData()
            tv_proto.device_id = device_id
            tv_proto.display_name = device['device_name']
            tv_proto.is_active = device_id in active_subscription_ids
            tv_proto.tv_config.SetInParent()
            if device_id in drone_mode_tv_dict:
                tv_config = TVConfig(**drone_mode_tv_dict[device_id])
                tv_config.set_protobuf(tv_proto.tv_config)
            valid_tv_protos.append(tv_proto)
            json_obj = MessageToDict(tv_proto,
                                     including_default_value_fields=True,
                                     use_integers_for_enums=True,
                                     preserving_proto_field_name=True)
            # since we're storing the user choices and input tokens as blobs,
            # when we deserialize from proto to dict, we need to json dumps each of the fields
            json_obj[constants.TV_CONFIG][constants.INPUT_TOKENS] = json.dumps(json_obj.get(constants.TV_CONFIG, {}).get(constants.INPUT_TOKENS, {}))
            json_obj[constants.TV_CONFIG][constants.USER_CHOICES] = json.dumps(json_obj.get(constants.TV_CONFIG, {}).get(constants.USER_CHOICES, {}))

            valid_tv_json.append(json_obj)

    LOGGER.debug('finished fetch valid tvs: valid_tv_protos=%s, valid_tv_json=%s',
                 valid_tv_protos,
                 valid_tv_json)
    defer.returnValue([valid_tv_protos, valid_tv_json])

@defer.inlineCallbacks
def validate_devices(device_ids,
                     request_context,
                     async_kvstore_client):
    """
    Function to determine if device ids are valid
    (subscribed to drone mode and in the registered_devices table)
    :param device_ids: the set of device ids to check
    :param request_context: request context used to make kvstore requests
    :param async_kvstore_client: async client used to make kvstore requests
    """

    # Check to see if devices are in registered_devices_table
    tv_list = yield get_registered_tvs(request_context.auth_header,
                                       request_context.current_user,
                                       async_kvstore_client,
                                       device_ids=device_ids)
    tv_list_ids = {registered_tv[constants.DEVICE_ID] for registered_tv in tv_list}

    errors = []
    LOGGER.debug('device_ids=%s, tv_list_ids=%s', device_ids, tv_list_ids)
    registered_set_difference = set()
    subscription_set_difference = set()
    if tv_list_ids != device_ids:
        registered_set_difference = device_ids - tv_list_ids
        errors.append('The tvs with ids={} are no longer registered to this instance'
                      .format(list(registered_set_difference)))
        if not tv_list_ids:
            raise SpacebridgeApiRequestError(errors[0],
                                             status_code=http.NOT_FOUND)

    tv_subscriptions = yield fetch_subscriptions(request_context.auth_header,
                                                 async_kvstore_client,
                                                 user_list=[request_context.current_user],
                                                 subscription_type=constants.DRONE_MODE_TV,
                                                 device_ids=device_ids)
    # Check to see if subscriptions are active
    subscription_ids = {subscription.device_id for subscription in tv_subscriptions}

    LOGGER.debug('device_ids=%s, subscription_ids=%s', device_ids, subscription_ids)
    if subscription_ids != device_ids:
        subscription_set_difference = device_ids - subscription_ids
        errors.append('The tvs with ids={} are no longer subscribed to drone mode'
                      .format(list(subscription_set_difference)))
        if not subscription_ids:
            raise SpacebridgeApiRequestError(' and '.join(errors),
                                             status_code=http.BAD_REQUEST)
    # if all tvs are invalid, but for different reasons
    if registered_set_difference.union(subscription_set_difference) == device_ids:
        raise SpacebridgeApiRequestError('The tvs with ids={} are all invalid: these ids={} are no longer registered to the instance and '
                                         'these={} are no longer subscribed to drone mode'
                                         .format(list(device_ids),
                                                 list(registered_set_difference),
                                                 list(subscription_set_difference)),
                                         status_code=http.BAD_REQUEST)

    defer.returnValue(errors)

@defer.inlineCallbacks
def activate_tv_bookmark(request_context, async_client_factory, bookmark_name):
    """
    Function to activate a TV bookmark
    :param request_context: request context used to make kvstore requests
    :param async_kvstore_client: async client used to make kvstore requests
    :param bookmark_name: tv bookmark name
    """
    # check for bookmark with existing name
    async_kvstore_client = async_client_factory.kvstore_client()
    bookmark_json = yield fetch_tv_bookmark(bookmark_name,
                                            request_context,
                                            async_kvstore_client,
                                            error_if_empty=True)
    LOGGER.debug('bookmark_json used for activating tv bookmark=%s', bookmark_json)
    bookmark_json_items = bookmark_json.get(constants.TV_CONFIG_MAP, {}).items()

    # update timestamp when activating
    device_ids = set()
    for device_id, item in bookmark_json_items:
        item[constants.TIMESTAMP] = datetime.now().strftime('%s')
        device_ids.add(device_id)
    errors = yield validate_devices(device_ids, request_context, async_kvstore_client)

    # create deep copy of config data so original doesn't get modified
    post_data = deepcopy(bookmark_json_items)

    # remove device id and add key to dict
    for device_id, config in post_data:
        LOGGER.debug('device_id=%s, config=%s', device_id, config)
        if constants.DEVICE_ID in config:
            del config[constants.DEVICE_ID]
        kvstore_key = b64_to_urlsafe_b64(device_id)
        config[constants.KEY] = kvstore_key

    device_ids = [device_id for device_id, _ in post_data]
    data = [config for _, config in post_data]

    # Update drone mode tvs kvstore collection with tv config data
    yield async_kvstore_client.async_batch_save_request(
        request_context.auth_header,
        constants.DRONE_MODE_TVS_COLLECTION_NAME,
        data,
        owner=request_context.current_user)

    # Send config updates to all devices in the bookmark and
    # all ipads registered to the current user
    yield process_subscriptions(request_context,
                                async_client_factory,
                                tv_device_ids=device_ids)
    if errors:
        LOGGER.error('Errors occurred during TV Bookmark Activate Request for bookmark_name=%s, errors=%s',
                     bookmark_name, errors)

        defer.returnValue(errors)

    LOGGER.info('Successful TV Bookmark Activate Request for bookmark_name=%s',
                bookmark_name)
    defer.returnValue(None)

@defer.inlineCallbacks
def fetch_tv_bookmark(bookmark_name, request_context, async_kvstore_client, error_if_empty=False):
    """
    Function to fetch tv bookmark data from kvstore
    :param bookmark_name: tv bookmark name
    :param request_context: request context used to make kvstore requests
    :param async_kvstore_client: async client used to make kvstore requests
    :param error_if_empty: Whether or not to error out if there is no data returned
    """
    query = {constants.NAME: bookmark_name}

    response = yield async_kvstore_client.async_kvstore_get_request(
        collection=constants.TV_BOOKMARK_COLLECTION_NAME,
        owner=request_context.current_user,
        params={constants.QUERY: json.dumps(query), constants.LIMIT: 1},
        auth_header=request_context.auth_header)

    yield check_and_raise_error(response, request_context, 'Get TV Bookmark')
    bookmark_json = yield response.json()
    if not bookmark_json and error_if_empty:
        raise SpacebridgeApiRequestError('Bookmark with name={} could not be found'
                                         .format(bookmark_name),
                                         status_code=http.NOT_FOUND)
    if bookmark_json:
        defer.returnValue(bookmark_json[0])
    defer.returnValue({})

@defer.inlineCallbacks
def send_drone_mode_subscription_update(auth_header,
                                        subscription,
                                        subscription_update,
                                        encryption_context,
                                        async_spacebridge_client,
                                        async_kvstore_client):
    """
    Function that sends a drone mode subscription update
    :param auth header: Authentication header used to fetch public
                        keys for destination device from kvstore
    :param subscription: Subscription channel is recieving an update
    :param subscription_update: Update data being sent
    :param encryption context: Used to encrypt the data
    @async_spacebridge_client: Spacebridge client used to send the request
    @async_kvstore_client: Kvstore client used to fetch public keys
    """

    signer = partial(sign_detached,
                     encryption_context.sodium_client,
                     encryption_context.sign_private_key())
    device_id_raw = base64.b64decode(subscription.device_id)
    _, receiver_encrypt_public_key = yield public_keys_for_device(device_id_raw, auth_header,
                                                                  async_kvstore_client)
    encryptor = partial(encrypt_for_send,
                        encryption_context.sodium_client,
                        receiver_encrypt_public_key)
    LOGGER.info("chimera subscription_update={}".format(subscription_update))

    sender_id = encryption_context.sign_public_key(transform=encryption_context.generichash_raw)
    headers = {'Content-Type': 'application/x-protobuf', 'Authorization': sender_id.encode("hex")}
    update_id = get_guid()
    request_id = get_guid()

    drone_mode_update = build_drone_mode_subscription_update(request_id,
                                                             subscription.key(),
                                                             update_id,
                                                             subscription_update)
    LOGGER.debug('drone_mode_update=%s', drone_mode_update)
    # build message to send through spacebridge send_message api
    send_message_request = build_send_subscription_update_request(
        device_id_raw, sender_id, request_id, drone_mode_update,
        encryptor, signer)
    # Send post request asynchronously
    LOGGER.info(
        'Drone Mode Subscription Update Sent. '
        'size_bytes=%s, request_id=%s, update_id=%s, subscription_id=%s',
        send_message_request.ByteSize(),
        request_id,
        update_id,
        subscription.key()
    )

    response = yield async_spacebridge_client.async_send_message_request(
        auth_header=SpacebridgeAuthHeader(sender_id),
        data=send_message_request.SerializeToString(),
        headers=headers)
    result_tuple = (response, subscription.key())
    defer.returnValue(result_tuple)

@defer.inlineCallbacks
def fetch_subscriptions(auth_header,
                        async_kvstore_client,
                        user_list=None,
                        subscription_type=None,
                        subscription_id=None,
                        device_ids=None):
    """
    Fetch drone mode subscription objects from kvstore collection [subscription]
    # It specifically does the following:
    # 1. Returns all drone mode subscriptions
    # 2. Returns all drone mode subcriptions of a certain type (ipad, tv)
    # 3. Returns all subscriptions given a list of ids
    :param auth_header: auth header used to authenticate to kvstore
    :param owner: collection owner
    :param async_kvstore_client: kvstore client used to make request
    :param subscription_type: Type of subscription to fetch (ipad, tv)
    :param subscription_id: subscription_id to fetch
    :param device_ids: device ids to fetch (must also provide subscription type)
    :return:
    """



    if subscription_type and subscription_id:
        raise SpacebridgeApiRequestError('You can only provide one of subscription type ' +
                                         'or subscription id to fetch subscriptions.',
                                         status_code=http.BAD_REQUEST)

    if device_ids and not subscription_type:
        raise SpacebridgeApiRequestError('You must provide a subscription type to filter by  ' +
                                         'device ids.', status_code=http.BAD_REQUEST)

    if device_ids and subscription_type:
        params = {
            constants.QUERY: json.dumps({
                constants.AND_OPERATOR: [
                    build_containedin_clause(constants.USER, user_list),
                    build_containedin_clause(constants.DEVICE_ID, device_ids),
                    {constants.SUBSCRIPTION_TYPE: subscription_type}
                ]
            })
        }
    elif subscription_type:
        params = {constants.QUERY: json.dumps({constants.SUBSCRIPTION_TYPE: subscription_type})}

    elif user_list:
        params = {
            constants.QUERY: json.dumps({
                constants.AND_OPERATOR: [
                    build_containedin_clause(constants.USER, user_list),
                    build_containedin_clause(constants.SUBSCRIPTION_TYPE, {constants.DRONE_MODE_IPAD,
                                                                           constants.DRONE_MODE_TV})
                ]
            })
        }
    else:
        params = {
            constants.QUERY: json.dumps(
                build_containedin_clause(constants.SUBSCRIPTION_TYPE, {constants.DRONE_MODE_IPAD,
                                                                       constants.DRONE_MODE_TV})
            )
        }

    response = yield async_kvstore_client.async_kvstore_get_request(
        collection=constants.SUBSCRIPTIONS_COLLECTION_NAME,
        params=params,
        owner=constants.NOBODY,
        key_id=subscription_id,
        auth_header=auth_header)
    subscriptions = []
    if response.code == http.OK:
        response_json = yield response.json()
        if isinstance(response_json, list):
            subscriptions = [Subscription.from_json(subscription) for subscription in response_json]
        else:
            if response_json:
                subscriptions.append(Subscription.from_json(response_json))
    else:
        error = yield response.text()
        LOGGER.error("Unable to fetch_subscriptions. status_code=%s, error=%s",
                     response.code, error)

    LOGGER.debug('subscriptions in fetch_subscriptions=%s', subscriptions)
    defer.returnValue(subscriptions)

@defer.inlineCallbacks
def fetch_active_tv_configs(user_subscription_map, async_kvstore_client, request_context):
    """
    Fetch active tv configs based on
    subscription data
    :param user_subscription_map: Map from user to list of subscriptions
    :param async_kvstore_client: kvstore client used to make requests
    :param request_context: request context used for kvstore client
    @returns: tv_config_json_list
    """
    # fetch tv config data from drone mode tvs collection
    kvstore_requests = []
    LOGGER.debug('user_subscription_map=%s', user_subscription_map)
    for user, subscription_array in user_subscription_map.items():
        device_ids = [subscription.device_id for subscription in subscription_array]
        LOGGER.debug("device_ids in subscription array for user=%s: =%s", user, device_ids)


        kvstore_request = get_drone_mode_tvs(request_context,
                                             async_kvstore_client,
                                             device_ids=device_ids,
                                             user=user)
        kvstore_requests.append(kvstore_request)

    tv_config_json_list = []
    exceptions = []
    responses = yield defer.DeferredList(kvstore_requests, consumeErrors=True)
    for response in responses:
        if isinstance(response[1], Failure):
            exceptions.append(response[1])
        else:
            (_, tv_config_json) = response
            LOGGER.debug('response in fetch active config=%s', response)
            tv_config_json_list.extend(tv_config_json)
    LOGGER.debug('Finished fetching tv configs for subscription updates, '
                 'tv_config_json_list=%s', tv_config_json_list)
    if exceptions:
        LOGGER.error('Encountered exceptions fetching drone mode tv data: e=%s', exceptions)
    defer.returnValue(tv_config_json_list)

@defer.inlineCallbacks
def send_tv_config_update(tv_config,
                          subscription,
                          request_context,
                          encryption_context,
                          async_spacebridge_client,
                          async_kvstore_client):
    """Function to construct and send a single DroneMode TV Config
    subscription update event
    :param tv_config: TV config to update
    :param subscription: Subscription to update
    :param auth_header: auth heard usedto authenticate kvstore client
    :param encryption context: used to encrypt spacebridge message
    :param async_spacebridge client: used to send spacebridge message
    :param async_kvstore_client: usd to make kvstore request
    """
    LOGGER.debug('sending update for device_id=%s', tv_config.device_id)
    subscription_update = DroneModeTVEvent(data_object=tv_config,
                                           event_type=TVEventType.TV_CONFIG)
    response, subscription_key = yield send_drone_mode_subscription_update(request_context.system_auth_header,
                                                                           subscription,
                                                                           subscription_update,
                                                                           encryption_context,
                                                                           async_spacebridge_client,
                                                                           async_kvstore_client)

    yield check_and_raise_error(response, request_context, 'Send TV Subscription Update')
    LOGGER.debug('subscription_update=%s', subscription_update)
    defer.returnValue((response, subscription_key))

@defer.inlineCallbacks
def send_ipad_tvlist_update(tv_list,
                            subscription,
                            request_context,
                            encryption_context,
                            async_spacebridge_client,
                            async_kvstore_client):
    """Function to construct and send a single DroneMode iPad
    TVList subscription event
    :param tv_list: TV list to send in update
    :param subscription: Subscription to update
    :param auth_header: auth heard usedto authenticate kvstore client
    :param encryption context: used to encrypt spacebridge message
    :param async_spacebridge client: used to send spacebridge message
    :param async_kvstore_client: usd to make kvstore request
    """

    subscription_update = DroneModeiPadEvent(data_object=tv_list, event_type=IPadEventType.TV_LIST)
    response, subscription_key = yield send_drone_mode_subscription_update(request_context.system_auth_header,
                                                                           subscription,
                                                                           subscription_update,
                                                                           encryption_context,
                                                                           async_spacebridge_client,
                                                                           async_kvstore_client)

    yield check_and_raise_error(response, request_context, 'Send iPad Subscription Update')
    LOGGER.debug('subscription_update=%s', subscription_update)
    defer.returnValue((response, subscription_key))

@defer.inlineCallbacks
def send_device_update(subscription_update,
                       subscription_type,
                       subscription,
                       request_context,
                       encryption_context,
                       async_spacebridge_client,
                       async_kvstore_client):
    """Function to construct and send a single DroneMode iPad
    TVList subscription event
    :param tv_list: TV list to send in update
    :param subscription: Subscription to update
    :param auth_header: auth heard usedto authenticate kvstore client
    :param encryption context: used to encrypt spacebridge message
    :param async_spacebridge client: used to send spacebridge message
    :param async_kvstore_client: usd to make kvstore request
    """

    response, subscription_key = yield send_drone_mode_subscription_update(request_context.system_auth_header,
                                                                           subscription,
                                                                           subscription_update,
                                                                           encryption_context,
                                                                           async_spacebridge_client,
                                                                           async_kvstore_client)

    yield check_and_raise_error(response, request_context, 'Send {} Subscription Update'.format(subscription_type))
    LOGGER.debug('subscription_update=%s', subscription_update)
    defer.returnValue((response, subscription_key))

@defer.inlineCallbacks
def send_ipad_tvlist_updates(tv_list_map,
                             subscriptions,
                             encryption_context,
                             async_spacebridge_client,
                             async_kvstore_client,
                             request_context):
    """
    Function to send tv list subscription updates to
    the drone mode ipads
    :param tv_list_map: map of users to tv_lists so we send the right update to the right user
    :param subscriptions: list of subscriptions to update
    :param encryption context: used to encrypt spacebridge message
    :param async_spacebridge client: used to send spacebridge message
    :param async_kvstore_client: usd to make kvstore request
    :param request_context: used to make kvstore requests
    """
    request_list = []
    for subscription in subscriptions:
        # make sure we send the right tv list
        tv_list = tv_list_map[subscription.user]

        subscription_update = DroneModeiPadEvent(data_object=tv_list, event_type=IPadEventType.TV_LIST)
        request = send_device_update(subscription_update,
                                     constants.DRONE_MODE_IPAD,
                                     subscription,
                                     request_context,
                                     encryption_context,
                                     async_spacebridge_client,
                                     async_kvstore_client)
        request_list.append(request)

    yield process_subscription_deferredlist(request_list, constants.DRONE_MODE_IPAD)

@defer.inlineCallbacks
def create_user_tvlist_map(user_list, request_context, async_kvstore_client):
    """
    Function to create user to tvlist map
    so we send the right tvlist to the right
    users
    :param user_list: User list to iterate over
    :param request_context: request context used to make kvstore request
    :param async_kvstore_cient: kvstore client used to make request
    @return: tv_list_map
    """
    request_list = []
    for user in user_list:
        request = fetch_valid_tvs(request_context,
                                  async_kvstore_client,
                                  user=user)
        request_list.append(request)

    tv_list_map = {}
    exceptions = []
    responses = yield defer.DeferredList(request_list, consumeErrors=True)
    for (idx, response) in enumerate(responses):
        if isinstance(response[1], Failure):
            exceptions.append((user_list[idx], response[1]))
        else:
            (_, (_, tv_list_json)) = response

            LOGGER.debug('tv_list_json=%s', tv_list_json)
            tv_list_map[user_list[idx]] = TVList(tv_list_json)
    if exceptions:
        LOGGER.error('Encountered exceptions fetching tv_list subscriptions, e=%s',
                     ['user={}, exception={}'.format(exception[0],
                                                     exception[1]) for exception in exceptions])
    LOGGER.debug('tv_list_map=%s', tv_list_map)
    defer.returnValue(tv_list_map)

@defer.inlineCallbacks
def send_tv_config_updates(tv_config_json_list,
                           subscription_user_device_map,
                           encryption_context,
                           async_spacebridge_client,
                           async_kvstore_client,
                           request_context):
    """
    Function to send tv config updates to
    the specified devices
    :param tv_config_json_list: list of tv configs to update
    :param subscription_user_device_map: map that gives us the correct subscription to update
    :param encryption context: used to encrypt spacebridge message
    :param async_spacebridge client: used to send spacebridge message
    :param async_kvstore_client: usd to make kvstore request
    :param auth_header: used to authenticate to make kvstore requests
    """
    request_list = []
    for tv_config_json in tv_config_json_list:
        tv_config = TVConfig(**tv_config_json)
        subscription = subscription_user_device_map.get(tv_config._user, {}).get(tv_config.device_id)
        if subscription:
            subscription_update = DroneModeTVEvent(data_object=tv_config,
                                                   event_type=TVEventType.TV_CONFIG)
            request = send_device_update(subscription_update,
                                         constants.DRONE_MODE_TV,
                                         subscription,
                                         request_context,
                                         encryption_context,
                                         async_spacebridge_client,
                                         async_kvstore_client)

            request_list.append(request)
    yield process_subscription_deferredlist(request_list, constants.DRONE_MODE_TV)

@defer.inlineCallbacks
def process_subscription_deferredlist(request_list, subscription_type):
    """
    Function to process pubsub deferredlist
    @requests: requests to process
    """
    requests = yield defer.DeferredList(request_list, consumeErrors=True)
    if not all(status for status, _ in requests):
        LOGGER.error('Failed to successfully update all devices (at least one failed), requests=%s', requests)
    failed_keys = []
    successful_keys = []
    for status, result in requests:
        if status:
            (response, subscription_key) = result
            if response.code != http.OK:
                failed_keys.append(subscription_key)
                text = yield response.text()
                LOGGER.error('response text for failed request=%s', text)
            else:
                successful_keys.append(subscription_key)

    if failed_keys:
        LOGGER.error('Failed to update subscriptions with these keys=%s, '
                     'but successfully updated subscriptions with these keys=%s',
                     failed_keys,
                     successful_keys)
    else:
        LOGGER.info('Successfully Updated %s subscriptions', subscription_type)

@defer.inlineCallbacks
def build_tv_subscription_updates(tv_subscriptions,
                                  request_context,
                                  async_kvstore_client):
    tv_subscription_user_device_map = {}
    for subscription in tv_subscriptions:
        # Don't rely on subscription user to be lowercase
        subscription_user = subscription.user.lower()
        if subscription_user not in tv_subscription_user_device_map:
            tv_subscription_user_device_map[subscription_user] = {}
        tv_subscription_user_device_map[subscription_user][subscription.device_id] = subscription

    LOGGER.debug('tv subscription_user_device_map=%s', tv_subscription_user_device_map)

    tv_user_subscription_map = {
        user: [
            v for _, v in subscription.items()
        ]
        for user, subscription in tv_subscription_user_device_map.items()
    }

    request_context = RequestContext(auth_header=request_context.system_auth_header,
                                     current_user=constants.ADMIN,
                                     system_auth_header=request_context.system_auth_header)

    tv_config_json_list = yield fetch_active_tv_configs(tv_user_subscription_map,
                                                        async_kvstore_client,
                                                        request_context)
    LOGGER.debug('tv_config_json_list=%s', tv_config_json_list)
    subscription_update_tuples = []
    for tv_config_json in tv_config_json_list:
        tv_config = TVConfig(**tv_config_json)
        tv_config_user = tv_config._user.lower()
        subscription = tv_subscription_user_device_map[tv_config_user][tv_config.device_id]
        subscription_update = DroneModeTVEvent(data_object=tv_config,
                                               event_type=TVEventType.TV_CONFIG)
        subscription_update_tuples.append((subscription, subscription_update))
    defer.returnValue(subscription_update_tuples)

@defer.inlineCallbacks
def build_ipad_subscription_updates(ipad_subscriptions,
                                    request_context,
                                    async_kvstore_client):
    users = list({subscription.user.lower() for subscription in ipad_subscriptions})
    tv_list_map = yield create_user_tvlist_map(users, request_context, async_kvstore_client)
    subscription_update_tuples = []
    for subscription in ipad_subscriptions:
        # make sure we send the right tv list
        tv_list = tv_list_map[subscription.user.lower()]

        subscription_update = DroneModeiPadEvent(data_object=tv_list, event_type=IPadEventType.TV_LIST)
        subscription_update_tuples.append((subscription, subscription_update))
    defer.returnValue(subscription_update_tuples)

@defer.inlineCallbacks
def send_updates(subscription_update_tuples,
                 encryption_context,
                 async_client_factory,
                 request_context,
                 subscription_type):
    """
    Function to send drone_mode subscription updates to
    the appropriate devices
    :param subscription_update_tuples: list of subscriptions, subscription_update tuples
    :param encryption context: used to encrypt spacebridge message
    :param async_spacebridge client: used to send spacebridge message
    :param async_kvstore_client: usd to make kvstore request
    :param request_context: Used to make kvstore requests
    """
    async_spacebridge_client = async_client_factory.spacebridge_client()
    async_kvstore_client = async_client_factory.kvstore_client()
    request_list = []
    for subscription, subscription_update in subscription_update_tuples:
        request = send_device_update(subscription_update,
                                     subscription_type,
                                     subscription,
                                     request_context,
                                     encryption_context,
                                     async_spacebridge_client,
                                     async_kvstore_client)
        request_list.append(request)

    yield process_subscription_deferredlist(request_list, subscription_type)

@defer.inlineCallbacks
def process_subscriptions(request_context,
                          async_client_factory,
                          encryption_context=None,
                          tv_device_ids=None,
                          tv_subscriptions=None,
                          ipad_subscriptions=None):
    """
    Function to send subscription updates to the appropriate tv
    and all ipads registered to the user
    :param tv_config: tv config to send
    :param request_context: request context used to make kvstore request
    :param async_client_factory: used to create spacebridge and kvstore client
    """
    async_kvstore_client = async_client_factory.kvstore_client()
    if not tv_subscriptions:
        tv_subscriptions = yield fetch_subscriptions(request_context.auth_header,
                                                     async_kvstore_client,
                                                     user_list=[request_context.current_user],
                                                     subscription_type=constants.DRONE_MODE_TV,
                                                     device_ids=tv_device_ids)


    LOGGER.debug('Active subscriptions%s: %s', ' for tv device_ids={}'.format(tv_device_ids) if tv_device_ids else '', tv_subscriptions)
    if tv_subscriptions:
        # create encryption context if not passed in
        if not encryption_context:
            sodium_client = SodiumClient()
            encryption_context = SplunkEncryptionContext(request_context.system_auth_header.session_token,
                                                         constants.SPACEBRIDGE_APP_NAME,
                                                         sodium_client)


        tv_subscription_tuples = yield build_tv_subscription_updates(tv_subscriptions,
                                                                     request_context,
                                                                     async_client_factory.kvstore_client())
        yield send_updates(tv_subscription_tuples,
                           encryption_context,
                           async_client_factory,
                           request_context,
                           constants.DRONE_MODE_TV)


    # Fetch active iPad subscriptions
    if not ipad_subscriptions:
        ipad_subscriptions = yield fetch_subscriptions(request_context.auth_header,
                                                       async_kvstore_client,
                                                       user_list=[request_context.current_user],
                                                       subscription_type=constants.DRONE_MODE_IPAD)
    if ipad_subscriptions:
        ipad_subscription_tuples = yield build_ipad_subscription_updates(ipad_subscriptions,
                                                                         request_context,
                                                                         async_client_factory.kvstore_client())
        yield send_updates(ipad_subscription_tuples,
                           encryption_context,
                           async_client_factory,
                           request_context,
                           constants.DRONE_MODE_IPAD)

@defer.inlineCallbacks
def remove_from_grid(tv_config,
                     device_ids,
                     request_context,
                     async_kvstore_client,
                     timestamp=None):
    """
    Function to remove a device from a grid configuration
    :param tv_config: config representing device being removed
    :param device_ids: device ids in tv_config grid
    :param request_context: request_context used to make kvstore request
    :param async_kvstore_client: kvstore client used to make request
    :param timestamp: timestamp to set in config
    """
    if not timestamp:
        timestamp = datetime.now().strftime('%s')
    if tv_config.device_id in device_ids:
        device_ids.remove(tv_config.device_id)
    # if it's currently the captain, clear out the
    # captain fields  so a new "election" will occur
    if tv_config.captain_id == tv_config.device_id:
        captain_url = ''
        captain_id = ''
    else:
        captain_id = tv_config.captain_id
        captain_url = tv_config.captain_url
    # store the update in kvstore
    yield update_grid_members(request_context,
                              async_kvstore_client,
                              device_ids,
                              captain_id,
                              captain_url,
                              timestamp)
    defer.returnValue(device_ids)

@defer.inlineCallbacks
def update_grid_members(request_context,
                        async_kvstore_client,
                        device_ids,
                        captain_id,
                        captain_url,
                        timestamp,
                        user=None):
    """
    Function to update the grid members
    with the correct captain id, captain url, and device
    ids data

    :param request_context: used to make kvstore request
    :param async_kvstore_client: client used to make kvstore request
    @device_ids: device ids to update
    @captain_id: captain id
    @captain_url: captain url
    """
    if not user:
        user = request_context.current_user
    tvs = yield get_drone_mode_tvs(request_context,
                                   async_kvstore_client,
                                   device_ids=device_ids,
                                   user=user)
    for tv in tvs:
        # if grid was deleted or if this somehow doesn't exist, don't do anything.
        if constants.TV_GRID in tv:
            tv[constants.TV_GRID][constants.DEVICE_IDS] = device_ids
            tv[constants.CAPTAIN_URL] = captain_url
            tv[constants.CAPTAIN_ID] = captain_id
            tv[constants.TIMESTAMP] = timestamp
    written_ids = yield async_kvstore_client.async_batch_save_request(
        request_context.system_auth_header,
        constants.DRONE_MODE_TVS_COLLECTION_NAME,
        tvs,
        owner=user)
    LOGGER.debug("updated tvs:%s", written_ids)
    defer.returnValue(written_ids)

@defer.inlineCallbacks
def check_for_dead_captains(request_context,
                            async_kvstore_client,
                            user_list):
    """
    Function to check for dead captains.  May their souls
    rest in peace.

    :param request context: used to make kvstore requests
    :param async_kvstore_client: clients used to make kvstore requests
    :param user_list: users who have registered a drone mode ipad
    """
    tv_requests = []
    current_tvs_map = {}
    exceptions = []
    for user in user_list:
        current_tvs = fetch_valid_tvs(request_context,
                                      async_kvstore_client,
                                      user=user)
        tv_requests.append(current_tvs)

    responses = yield defer.DeferredList(tv_requests, consumeErrors=True)

    for idx, response in enumerate(responses):
        if isinstance(response[1], Failure):
            exceptions.append(response[1])
        else:
            (_, (_, tv_json)) = response
            current_tvs_map[user_list[idx]] = tv_json
    LOGGER.debug('Finished fetching current tvs map=%s', current_tvs_map)
    if exceptions:
        LOGGER.error('Encountered exceptions fetching tvs, e=%s', exceptions)

    captain_death_requests = []
    for user, tv_data_list in current_tvs_map.items():
        for tv_data in tv_data_list:
            if (not tv_data[constants.IS_ACTIVE] and
                    tv_data.get(constants.TV_CONFIG, {}).get(constants.CAPTAIN_ID) ==
                    tv_data.get(constants.DEVICE_ID) and
                    has_grid(tv_data.get(constants.TV_CONFIG), is_json=True)):
                # captain died, we need to elect a new one
                # this time, we keep the device id list the same, in case the captain comes back
                device_ids = tv_data[constants.TV_CONFIG][constants.TV_GRID][constants.DEVICE_IDS]
                captain_id = captain_url = ''
                timestamp = datetime.now().strftime('%s')
                captain_death_request = update_grid_members(request_context,
                                                            async_kvstore_client,
                                                            device_ids,
                                                            captain_id,
                                                            captain_url,
                                                            timestamp,
                                                            user=user)
                captain_death_requests.append(captain_death_request)
    responses = yield defer.DeferredList(captain_death_requests, consumeErrors=True)
    updated_ids = []
    for idx, response in enumerate(responses):
        if isinstance(response[1], Failure):
            exceptions.append(response[1])
        else:
            (_, written_ids) = response
            updated_ids.extend(written_ids)
    if exceptions:
        LOGGER.error('Encountered exceptions fetching tvs, e=%s', exceptions)
    LOGGER.debug('updated devices for captain election, written_ids=%s', updated_ids)

@defer.inlineCallbacks
def create_subscription_credentials(request_context, subscription_id, async_client_factory):
    async_kvstore_client = async_client_factory.kvstore_client()
    async_splunk_client = async_client_factory.splunk_client()

    if isinstance(request_context.auth_header, JWTAuthHeader):
        LOGGER.debug("JWTAuthHeader detected. Setting session_key_type = %s", constants.JWT_TOKEN_TYPE)
        session_type = constants.JWT_TOKEN_TYPE
        session_key = request_context.auth_header.token
    else:
        LOGGER.debug("SplunkAuthHeader detected. Setting session_key_type = %s", constants.SPLUNK_SESSION_TOKEN_TYPE)
        session_type = constants.SPLUNK_SESSION_TOKEN_TYPE
        session_key = yield get_splunk_cookie(request_context=request_context,
                                              async_splunk_client=async_splunk_client,
                                              username=request_context.auth_header.username,
                                              password=request_context.auth_header.password)

    now = get_current_timestamp_str()


    auth = SubscriptionCredential(subscription_id=subscription_id,
                                  session_key=session_key,
                                  session_type=session_type,
                                  shard_id=request_context.shard_id,
                                  last_update_time=now,
                                  _key=subscription_id)

    # create subscription and return _key
    response = yield async_kvstore_client.async_kvstore_post_request(
        owner=request_context.current_user,
        collection=constants.SUBSCRIPTION_CREDENTIALS_COLLECTION_NAME,
        data=auth.to_json(),
        auth_header=request_context.auth_header)

    if response.code == http.OK or response.code == http.CREATED or response.code == http.CONFLICT:
        LOGGER.debug("Subscription Created. subscription_id=%s", auth.subscription_id)
        defer.returnValue(auth)
    else:
        error = yield response.text()
        error_message = "Failed to create Subscription credentials. status_code={}, error={}".format(
            response.code, error)
        raise SpacebridgeApiRequestError(error_message)
