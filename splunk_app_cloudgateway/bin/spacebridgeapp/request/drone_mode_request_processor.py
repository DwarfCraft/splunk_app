"""
(C) 2020 Splunk Inc. All rights reserved.

Module to process App List Requests
"""
import json
import base64
from twisted.internet import defer
from twisted.web import http
from twisted.python.failure import Failure
from cloudgateway.private.sodium_client import SodiumClient
from cloudgateway.splunk.encryption import SplunkEncryptionContext
from spacebridgeapp.util import constants
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.py23 import b64encode_to_str, urlsafe_b64encode_to_str, \
                                     b64_to_urlsafe_b64, urlsafe_b64_to_b64
from spacebridgeapp.util.error_utils import check_and_raise_error
from spacebridgeapp.util.time_utils import get_expiration_timestamp_str, get_current_timestamp_str
from spacebridgeapp.drone_mode.drone_mode_subscription_requests import (
    fetch_valid_tvs, activate_tv_bookmark, fetch_tv_bookmark,
    send_drone_mode_subscription_update, fetch_subscriptions,
    process_subscriptions, update_grid_members,
    validate_devices, get_registered_tvs,
    create_subscription_credentials, remove_from_grid)
from spacebridgeapp.drone_mode.drone_mode_utils import get_drone_mode_tvs, has_grid
from spacebridgeapp.data.subscription_data import Subscription, DroneModeTVEvent
from spacebridgeapp.drone_mode.data.drone_mode_data import TVConfig, TVBookmark, StartMPCBroadcast, TVInteraction
from spacebridgeapp.drone_mode.data.enums import TVEventType, TVInteractionType
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError


LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_drone_mode_request_processor.log",
                       "drone_mode_request_processor")

@defer.inlineCallbacks
def process_tv_get_request(request_context,
                           client_single_request,
                           single_server_response,
                           async_kvstore_client):
    """
    This method will process a tvGetRequest.
    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_kvstore_client: kvstore client used to make kvstore requests
    """


    device_id = client_single_request.tvGetRequest.deviceId
    device_ids = [device_id] if device_id else None
    valid_tv_protos, _ = yield fetch_valid_tvs(request_context,
                                               async_kvstore_client,
                                               tv_ids=device_ids)
    single_server_response.tvGetResponse.tvData.extend(valid_tv_protos)

@defer.inlineCallbacks
def process_tv_captain_url_request(request_context,
                                   client_single_request,
                                   single_server_response,
                                   async_client_factory):
    """
    This method processes captain url requests from drone mode TVs.
    It is called when picking a captain when a grid request is activated, and
    reelecting a captain when the captain dies.

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_client factory: factory class used to generate kvstore and spacebridge clients
    """
    captain_url_request = client_single_request.tvCaptainUrlRequest
    update_flag = captain_url_request.updateFlag
    captain_id = client_single_request.tvCaptainUrlRequest.captainId
    async_kvstore_client = async_client_factory.kvstore_client()

    # fetch tv config for captain id
    tvs = yield get_drone_mode_tvs(request_context,
                                   async_kvstore_client,
                                   device_ids=[captain_id])
    if not tvs:
        raise SpacebridgeApiRequestError('Invalid captain id provided. captain_id={}'.format(captain_id),
                                         status_code=http.BAD_REQUEST)
    tv = tvs[0]

    LOGGER.debug('tvs in captain url request = %s', tvs)
    tv_config = TVConfig(**tv)

    # if we're updating the captain url, or if we're trying to be elected
    # captain and no one is yet, we do the same thing
    if not (tv_config.captain_url or tv_config.captain_id) or update_flag:
        device_ids = tv_config.tv_grid['device_ids']
        captain_url = captain_url_request.captainUrl
        timestamp = get_current_timestamp_str()
        yield update_grid_members(request_context,
                                  async_kvstore_client,
                                  device_ids,
                                  captain_id,
                                  captain_url,
                                  timestamp)
        yield process_subscriptions(request_context,
                                    async_client_factory,
                                    tv_device_ids=device_ids)

    else:
        LOGGER.debug('captain url already set for device_id=%s, doing nothing', tv_config.device_id)
    single_server_response.tvCaptainUrlResponse.SetInParent()

@defer.inlineCallbacks
def process_tv_config_bulk_set_request(request_context,
                                       client_single_request,
                                       single_server_response,
                                       async_client_factory):
    """
    Bulk tv config set request.  Used to bulk send tv config set requests
    when we're setting a grid configuration

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_client factory: factory class used to generate kvstore and spacebridge clients
    """

    async_kvstore_client = async_client_factory.kvstore_client()
    tv_config_protos = client_single_request.tvConfigBulkSetRequest.tvConfig
    is_token_update = client_single_request.tvConfigBulkSetRequest.isTokenUpdate
    LOGGER.debug('tv_config_protos=%s', tv_config_protos)
    device_ids = {proto.device_id for proto in tv_config_protos}
    timestamp = get_current_timestamp_str()
    warnings = yield validate_devices(device_ids, request_context, async_kvstore_client)
    # Before setting configs, we need to check if
    # we're setting configs on tvs that are currently in
    # grid configurations, so we need to fetch them.
    # This logic is ignored if we're doing a token update

    existing_grids_to_update = set()
    if not is_token_update:
        tvs = yield get_drone_mode_tvs(request_context,
                                       async_kvstore_client,
                                       device_ids=device_ids)
        if tvs:
            requests = []
            for tv in tvs:
                existing_config = TVConfig(**tv)
                # If it's a grid, we remove it from the existing grid list
                if has_grid(tv, is_json=True):
                    grid_device_ids = existing_config.tv_grid[constants.DEVICE_IDS]
                    existing_grids_to_update.update(grid_device_ids)
                    request = remove_from_grid(tv_config=existing_config,
                                               device_ids=grid_device_ids,
                                               request_context=request_context,
                                               async_kvstore_client=async_kvstore_client,
                                               timestamp=timestamp)
                    requests.append(request)

            if requests:
                exceptions = []
                responses = yield defer.DeferredList(requests, consumeErrors=True)
                for response in responses:
                    if isinstance(response[1], Failure):
                        exceptions.append(response[1])
                LOGGER.debug('Finished updating modified tvs')
                if exceptions:
                    LOGGER.error('Encountered exceptions updating tvs, e=%s', exceptions)
                    # if we couldn't update any of the existing configs, we should not continue the request
                    if len(exceptions) == len(requests):
                        raise SpacebridgeApiRequestError('Unable to update all existing tv configs',
                                                         status_code=http.INTERNAL_SERVER_ERROR)



    post_data = []
    for tv_config_proto in tv_config_protos:
        tv_config = TVConfig()
        tv_config.from_protobuf(tv_config_proto)

        # set timestamp here
        tv_config.timestamp = timestamp
        tv_config_json = json.loads(tv_config.to_json())

        # delete device id
        if constants.DEVICE_ID in tv_config_json:
            del tv_config_json[constants.DEVICE_ID]

        LOGGER.debug('tv_config_json=%s', tv_config_json)

        # convert device id to urlsafe b64 encoded to use as kvstore key
        urlsafe_b64encoded_device_id = b64_to_urlsafe_b64(tv_config.device_id)
        tv_config_json[constants.KEY] = urlsafe_b64encoded_device_id
        post_data.append(tv_config_json)
    LOGGER.debug('post_data=%s', post_data)
    updated_keys = yield async_kvstore_client.async_batch_save_request(
        request_context.system_auth_header,
        constants.DRONE_MODE_TVS_COLLECTION_NAME,
        post_data,
        owner=request_context.current_user)
    ids_to_update = {urlsafe_b64_to_b64(key) for key in updated_keys}
    ids_to_update.update(existing_grids_to_update)
    ids_to_update = list(ids_to_update)

    LOGGER.debug('ids_to_update=%s', ids_to_update)
    yield process_subscriptions(request_context,
                                async_client_factory,
                                tv_device_ids=ids_to_update)
    if warnings:
        single_server_response.tvConfigBulkSetResponse.warnings.extend(warnings)
    single_server_response.tvConfigBulkSetResponse.SetInParent()

@defer.inlineCallbacks
def process_tv_config_set_request(request_context,
                                  client_single_request,
                                  single_server_response,
                                  async_client_factory):
    """
    This method will process a tvConfigSetRequest.

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_client factory: factory class used to generate kvstore and spacebridge clients
    """
    async_kvstore_client = async_client_factory.kvstore_client()
    tv_config_set_request = client_single_request.tvConfigSetRequest

    tv_config_proto = tv_config_set_request.tvConfig
    tv_config = TVConfig()
    tv_config.from_protobuf(tv_config_proto)
    timestamp = get_current_timestamp_str()
    ids_to_update = [tv_config.device_id]
    # Check to make sure device is valid before proceeding
    yield validate_devices(set(ids_to_update), request_context, async_kvstore_client)

    # Before setting config, we need to check if
    # we're setting a config on a tv that is currently in
    # a grid configuration, so we need to fetch it.
    tvs = yield get_drone_mode_tvs(request_context,
                                   async_kvstore_client,
                                   device_ids=[tv_config.device_id])

    if tvs:
        tv = tvs[0]
        existing_config = TVConfig(**tv)
        # If it's a grid, we remove it from the existing grid list,
        if has_grid(tv, is_json=True) and not has_grid(tv_config_proto):
            device_ids = ids_to_update = existing_config.tv_grid[constants.DEVICE_IDS]
            yield remove_from_grid(tv_config=existing_config,
                                   device_ids=device_ids,
                                   request_context=request_context,
                                   async_kvstore_client=async_kvstore_client,
                                   timestamp=timestamp)

    # set timestamp here
    tv_config.timestamp = timestamp
    tv_config_json = json.loads(tv_config.to_json())

    # delete device id
    if constants.DEVICE_ID in tv_config_json:
        del tv_config_json[constants.DEVICE_ID]

    LOGGER.debug('tv_config_json=%s', tv_config_json)

    # convert device id to urlsafe b64 encoded to use as kvstore key
    urlsafe_b64encoded_device_id = b64_to_urlsafe_b64(tv_config.device_id)
    tv_config_json[constants.KEY] = urlsafe_b64encoded_device_id

    response = yield async_kvstore_client.async_kvstore_post_or_update_request(
        constants.DRONE_MODE_TVS_COLLECTION_NAME,
        json.dumps(tv_config_json),
        request_context.system_auth_header,
        key_id=urlsafe_b64encoded_device_id,
        owner=request_context.current_user)

    yield check_and_raise_error(response,
                                request_context,
                                'Write TV Config',
                                valid_codes=[http.OK, http.CREATED])

    single_server_response.tvConfigSetResponse.SetInParent()
    # update tv subscription for config we just created
    # (and affected grid device ids, if applicable) as well as
    # all ipads registered to current user
    yield process_subscriptions(request_context,
                                async_client_factory,
                                tv_device_ids=ids_to_update)

    LOGGER.info("Successful TV Config Set Request for device id=%s", tv_config.device_id)

@defer.inlineCallbacks
def process_tv_config_delete_request(request_context,
                                     client_single_request,
                                     single_server_response,
                                     async_client_factory):
    """This method will process a tvConfigDeleteRequest.

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_client factory: factory class used to generate kvstore and spacebridge clients
    """
    async_kvstore_client = async_client_factory.kvstore_client()

    tv_config_delete_request = client_single_request.tvConfigDeleteRequest

    device_ids = tv_config_delete_request.deviceId

    LOGGER.debug('device_ids to delete=%s', device_ids)
    yield validate_devices(set(device_ids), request_context, async_kvstore_client)
    # need to fetch configs before deleting to make sure we're not deleting the captain
    # and orphaning the workers, if so, for each one that is a captain, 
    # we need to fetch the other configs in the grid
    # delete the to be deleted captain from the device_id list, and update
    # the existing members of the grid

    tvs = yield get_drone_mode_tvs(request_context, async_kvstore_client, device_ids=device_ids)
    # fetch configs from kvstore
    # check to see if they are currently captain
    for tv in tvs:
        raw_id = base64.urlsafe_b64decode(str(tv[constants.KEY]))
        encoded_id = b64encode_to_str(raw_id)
        tv[constants.DEVICE_ID] = encoded_id

        if (has_grid(tv, is_json=True)):
            tv_config = TVConfig(**tv)
            grid_ids = tv.get(constants.TV_GRID, {}).get(constants.DEVICE_IDS, [])
            yield remove_from_grid(tv_config=tv_config,
                                   device_ids=grid_ids,
                                   request_context=request_context,
                                   async_kvstore_client=async_kvstore_client)

    entries_to_delete = []

    for device_id in device_ids:
        kvstore_key = b64_to_urlsafe_b64(device_id)
        post_data = {constants.KEY: kvstore_key}
        entries_to_delete.append(post_data)

    deleted_ids = yield async_kvstore_client.async_batch_save_request(
        request_context.system_auth_header,
        constants.DRONE_MODE_TVS_COLLECTION_NAME,
        entries_to_delete,
        owner=request_context.current_user)
    deleted_device_ids = [urlsafe_b64_to_b64(deleted_id) for deleted_id in deleted_ids]
    if deleted_device_ids:
        single_server_response.tvConfigDeleteResponse.deletedIds.extend(deleted_device_ids)

    if not deleted_ids:
        raise SpacebridgeApiRequestError('None of the device_ids={} were deleted'.format(device_ids), status_code=http.INTERNAL_SERVER_ERROR)

    elif len(deleted_ids) != len(device_ids):
        kvstore_keys = {b64_to_urlsafe_b64(device_id) for device_id in device_ids}
        LOGGER.error('TV configs with these ids: %s were deleted, '
                     'while TV configs with these ids: %s were not.',
                     deleted_ids, list(kvstore_keys-set(deleted_ids)))
    # update current deleted tv subscriptions and
    # all ipads registered to current user

    yield process_subscriptions(request_context,
                                async_client_factory,
                                tv_device_ids=device_ids)


    LOGGER.info('Successful TV Config Delete Request for device_ids=%s', deleted_device_ids)

@defer.inlineCallbacks
def process_tv_bookmark_get_request(request_context,
                                    client_single_request,
                                    single_server_response,
                                    async_kvstore_client):
    """
    This method will process a tvBookmarkGetRequest.

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_kvstore_client: kvstore client used to make kvstore requests
    """

    if client_single_request.tvBookmarkGetRequest.bookmarkName:
        bookmark_name = client_single_request.tvBookmarkGetRequest.bookmarkName
        params = {constants.QUERY: json.dumps({constants.NAME: bookmark_name}), constants.LIMIT: 1}
    else:
        bookmark_name = None
        params = None
    LOGGER.debug('bookmark_name=%s', bookmark_name)

    response = yield async_kvstore_client.async_kvstore_get_request(
        collection=constants.TV_BOOKMARK_COLLECTION_NAME,
        owner=request_context.current_user,
        params=params,
        auth_header=request_context.auth_header)
    yield check_and_raise_error(response, request_context, 'Fetch TV Bookmark')
    tv_bookmarks = yield response.json()
    if not tv_bookmarks and bookmark_name:
        raise SpacebridgeApiRequestError('Could not find any bookmarks for the supplied request',
                                         status_code=http.NOT_FOUND)

    if bookmark_name:
        # Fetch only first element since we limit our query to one, and bookmarks are unique by name
        bookmark = tv_bookmarks[0]
        LOGGER.debug('bookmark=%s', bookmark)
        proto = yield construct_tv_bookmark_proto(bookmark)
        single_server_response.tvBookmarkGetResponse.tvBookmark.extend([proto])
    else:
        proto_list = []
        for bookmark in tv_bookmarks:
            proto = yield construct_tv_bookmark_proto(bookmark)
            proto_list.append(proto)

        single_server_response.tvBookmarkGetResponse.tvBookmark.extend(proto_list)

    LOGGER.info('Successful TV Bookmark Get Request. Bookmark=%s', bookmark_name)

@defer.inlineCallbacks
def process_tv_bookmark_set_request(request_context,
                                    client_single_request,
                                    single_server_response,
                                    async_kvstore_client):
    """
    This method will process a tvBookmarkSetRequest.

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_kvstore_client: kvstore client used to make kvstore requests
    """

    # save bookmark data to kvstore
    response = yield save_bookmark_to_kvstore(client_single_request,
                                              request_context,
                                              async_kvstore_client)

    yield check_and_raise_error(response,
                                request_context,
                                'Set TV Bookmark',
                                valid_codes=[http.OK, http.CREATED])

    single_server_response.tvBookmarkSetResponse.SetInParent()
    LOGGER.info('Successful TV Bookmark Set Request.')

@defer.inlineCallbacks
def process_tv_bookmark_delete_request(request_context,
                                       client_single_request,
                                       single_server_response,
                                       async_kvstore_client):
    """
    This method will process a tvBookmarkDeleteRequest.

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_kvstore_client: kvstore client used to make kvstore requests
    """

    tv_bookmark_delete_request = client_single_request.tvBookmarkDeleteRequest
    bookmark_name = tv_bookmark_delete_request.bookmarkName

    params = {constants.QUERY: json.dumps({constants.NAME: bookmark_name})}

    response = yield async_kvstore_client.async_kvstore_delete_request(
        collection=constants.TV_BOOKMARK_COLLECTION_NAME,
        params=params,
        owner=request_context.current_user,
        auth_header=request_context.system_auth_header)

    yield check_and_raise_error(response, request_context, 'Delete TV Bookmark')

    single_server_response.tvBookmarkDeleteResponse.SetInParent()
    LOGGER.info('Successful TV Bookmark Delete Request for bookmark name=%s', bookmark_name)

@defer.inlineCallbacks
def save_bookmark_to_kvstore(client_single_request, request_context, async_kvstore_client):
    """
    Function to write bookmark data
    to kvstore
    :param client_single_request: request object
    :param request_context: request context used to make kvstore request
    :param async_kvstore_client: client used to make kvstore request
    :return response:

    client passes in name, description, and device ids he wants to bookmark
    backend checks to see if there is an existing bookmark with the name given
    if so, and no overwrite flag is passed in, we error out
    if not, or if overwrite flag passed in, we continue

    for each of the device ids, we read what's in kvstore in the drone_mode_tvs collection
    for that config, and add it to the tv config map
    we error out of any of the device ids failed to fetch
    once we've gotten all of the configs, we save the bookmark
    """
    request = client_single_request.tvBookmarkSetRequest
    name = request.name
    LOGGER.debug('start of save bookmark with name=%s', name)
    description = request.description
    device_ids = request.deviceIds
    tv_config_map = yield create_tv_config_map(device_ids, async_kvstore_client, request_context)
    if not tv_config_map:
        raise SpacebridgeApiRequestError('No valid tv config device ids were provided. Device_ids={}'.format(device_ids),
                                         status_code=http.BAD_REQUEST)
    tv_bookmark = TVBookmark(name=name,
                             tv_config_map=tv_config_map,
                             description=description)

    LOGGER.debug('tv_bookmark=%s', tv_bookmark)
    tv_bookmark_json = json.loads(tv_bookmark.to_json())

    # check for bookmark with existing name
    existing_bookmark_json = yield fetch_tv_bookmark(name, request_context, async_kvstore_client)
    LOGGER.debug('existing_bookmark_json=%s', existing_bookmark_json)
    if existing_bookmark_json and request.overwrite:
        tv_bookmark_json[constants.KEY] = key_id = existing_bookmark_json[constants.KEY]
    elif existing_bookmark_json:
        raise SpacebridgeApiRequestError('An entry with this name already exists, name={}'.format(name),
                                         status_code=http.CONFLICT)
    else:
        key_id = None

    response = yield async_kvstore_client.async_kvstore_post_or_update_request(
        constants.TV_BOOKMARK_COLLECTION_NAME,
        json.dumps(tv_bookmark_json),
        request_context.system_auth_header,
        key_id=key_id,
        owner=request_context.current_user)

    defer.returnValue(response)

def construct_tv_bookmark_proto(bookmark):
    """
    Function to construct request params from tv bookmark dictionary
    :param bookmark: tv bookmark json
    :return tv bookmark proto:
    """

    tv_bookmark = TVBookmark(tv_config_map=bookmark[constants.TV_CONFIG_MAP],
                             description=bookmark[constants.BOOKMARK_DESCRIPTION],
                             name=bookmark[constants.NAME])
    return tv_bookmark.to_protobuf()

@defer.inlineCallbacks
def create_tv_config_map(device_ids, async_kvstore_client, request_context):
    """
    Function to create tv config map for initializing TVBookmark class
    :param device_ids: device ids to fetch tv configs for
    :param request_context: Used to authenticate kvstore requests
    :param async_kvstore_client: kvstore client used to make kvstore requests
    """
    # When we are setting a tv bookmark, we're only given device ids
    tv_config_map = {}
    tv_configs = yield get_drone_mode_tvs(request_context,
                                          async_kvstore_client,
                                          device_ids=device_ids)

    LOGGER.debug('device_ids in create_tv_config_map=%s', device_ids)
    LOGGER.debug('tv_configs in create_tv_config_map=%s', tv_configs)
    for tv_config in tv_configs:
        device_id = b64encode_to_str(base64.urlsafe_b64decode(str(tv_config.get(constants.KEY))))
        LOGGER.debug('tv_config for device_id=%s is: %s', device_id, tv_config)
        # Don't save captain id and captain url.  bookmark should be agnostic to this concept
        # only upon activation should we care about the captain stuff. This way, when we activate
        # a config in a grid configuration, it starts off with no captain data, and their for a captain
        # is immediately elected.
        if not all(key in tv_config for key in TVConfig.required_kvstore_keys()):
            raise SpacebridgeApiRequestError('No config data exists for device_id={}'
                                             .format(device_id),
                                             status_code=http.NOT_FOUND)
        tv_config[constants.CAPTAIN_ID] = ''
        tv_config[constants.CAPTAIN_URL] = ''
        tv_config_object = TVConfig(**tv_config)
        tv_config_map[device_id] = json.loads(tv_config_object.to_json())

    defer.returnValue(tv_config_map)

@defer.inlineCallbacks
def process_tv_bookmark_activate_request(request_context,
                                         client_single_request,
                                         single_server_response,
                                         async_client_factory):
    """
    This method will process a TVBookmarkActivateRequest.

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_client factory: factory class used to generate kvstore and spacebridge clients
    """

    bookmark_name = client_single_request.tvBookmarkActivateRequest.bookmarkName


    warnings = yield activate_tv_bookmark(request_context, async_client_factory, bookmark_name)
    if warnings:
        single_server_response.tvBookmarkActivateResponse.warnings.extend(warnings)

    single_server_response.tvBookmarkActivateResponse.SetInParent()
    LOGGER.info('Successful TV Bookmark Activate Request.')

@defer.inlineCallbacks
def process_tv_interaction_request(request_context,
                                   client_single_request,
                                   single_server_response,
                                   async_client_factory):
    """
    This Method will process a MPC Broadcast Request

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_client factory: factory class used to generate kvstore and spacebridge clients
    """

    async_kvstore_client = async_client_factory.kvstore_client()
    device_id = client_single_request.tvInteractionRequest.tvInteraction.device_id
    tv_interaction_proto = client_single_request.tvInteractionRequest.tvInteraction
    # determine type of interaction
    interaction_type = TVInteractionType.NONE
    speed = None
    if tv_interaction_proto.HasField(constants.SLIDESHOW_GOTO):
        interaction_type = TVInteractionType.GOTO

    elif tv_interaction_proto.HasField(constants.SLIDESHOW_STOP):
        interaction_type = TVInteractionType.STOP

    elif tv_interaction_proto.HasField(constants.SLIDESHOW_FORWARD):
        interaction_type = TVInteractionType.FORWARD

    elif tv_interaction_proto.HasField(constants.SLIDESHOW_BACK):
        interaction_type = TVInteractionType.BACK

    elif tv_interaction_proto.HasField(constants.SLIDESHOW_SPEED):
        interaction_type = TVInteractionType.SPEED
        speed = tv_interaction_proto.slideshow_speed.speed


    subscriptions = yield fetch_subscriptions(request_context.auth_header,
                                              async_kvstore_client,
                                              user_list=[request_context.current_user],
                                              subscription_type=constants.DRONE_MODE_TV,
                                              device_ids=[device_id])


    if not subscriptions:
        raise SpacebridgeApiRequestError('No active subscriptions for device_id={}'
                                         .format(device_id),
                                         status_code=http.BAD_REQUEST)

    async_spacebridge_client = async_client_factory.spacebridge_client()
    active_subscription = subscriptions[0]
    sodium_client = SodiumClient()
    encryption_context = SplunkEncryptionContext(request_context.system_auth_header.session_token,
                                                 constants.SPACEBRIDGE_APP_NAME,
                                                 sodium_client)
    tv_interaction = TVInteraction(device_id=device_id,
                                   interaction_type=interaction_type,
                                   speed=speed)
    subscription_update = DroneModeTVEvent(data_object=tv_interaction,
                                           event_type=TVEventType.TV_INTERACTION)
    response, subscription_key = yield send_drone_mode_subscription_update(request_context.system_auth_header,
                                                                           active_subscription,
                                                                           subscription_update,
                                                                           encryption_context,
                                                                           async_spacebridge_client,
                                                                           async_kvstore_client)
    yield check_and_raise_error(response, request_context, 'MPC Broadcast Request')
    single_server_response.tvInteractionResponse.SetInParent()

    LOGGER.info('Successfully sent mpc broadcast message to device_id=%s with subscription_key=%s',
                device_id,
                subscription_key)

@defer.inlineCallbacks
def process_mpc_broadcast_request(request_context,
                                  client_single_request,
                                  single_server_response,
                                  async_client_factory):
    """
    This Method will process a MPC Broadcast Request

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_client factory: factory class used to generate kvstore and spacebridge clients
    """

    async_kvstore_client = async_client_factory.kvstore_client()
    device_id = client_single_request.startMPCBroadcastRequest.deviceId

    subscriptions = yield fetch_subscriptions(request_context.auth_header,
                                              async_kvstore_client,
                                              user_list=[request_context.current_user],
                                              subscription_type=constants.DRONE_MODE_TV,
                                              device_ids=[device_id])
    if not subscriptions:
        raise SpacebridgeApiRequestError('No active subscriptions for device_id={}'
                                         .format(device_id),
                                         status_code=http.BAD_REQUEST)

    async_spacebridge_client = async_client_factory.spacebridge_client()
    active_subscription = subscriptions[0]
    sodium_client = SodiumClient()
    encryption_context = SplunkEncryptionContext(request_context.system_auth_header.session_token,
                                                 constants.SPACEBRIDGE_APP_NAME,
                                                 sodium_client)
    start_broadcast = StartMPCBroadcast(device_id=device_id)
    subscription_update = DroneModeTVEvent(data_object=start_broadcast,
                                           event_type=TVEventType.MPC_BROADCAST)
    response, subscription_key = yield send_drone_mode_subscription_update(request_context.system_auth_header,
                                                                           active_subscription,
                                                                           subscription_update,
                                                                           encryption_context,
                                                                           async_spacebridge_client,
                                                                           async_kvstore_client)
    yield check_and_raise_error(response, request_context, 'MPC Broadcast Request')
    single_server_response.startMPCBroadcastResponse.SetInParent()

    LOGGER.info('Successfully sent mpc broadcast message to device_id=%s with subscription_key=%s',
                device_id,
                subscription_key)

@defer.inlineCallbacks
def process_subscribe_drone_mode_tv(request_context,
                                    client_subscription_message,
                                    server_subscription_response,
                                    async_client_factory):
    """
    Process subscribe to drone mode tv events for a device id

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_client factory: factory class used to generate kvstore and spacebridge clients

    """

    LOGGER.debug('start of subscribe drone mode tv')
    async_kvstore_client = async_client_factory.kvstore_client()

    # base64 encode device id
    device_id = client_subscription_message.clientSubscribeRequest.droneModeTVSubscribe.deviceId
    encoded_device_id = b64encode_to_str(device_id)
    urlsafe_encoded_device_id = urlsafe_b64encode_to_str(device_id)

    # Grab TV data
    tv_data = yield get_registered_tvs(request_context.auth_header,
                                       request_context.current_user,
                                       async_kvstore_client)

    LOGGER.debug('raw device id=%s, encoded_device_id=%s, urlsafe_encoded_device_id=%s, tv_data=%s',
                 device_id,
                 encoded_device_id,
                 urlsafe_encoded_device_id,
                 tv_data)

    # validate that device is a valid apple tv registered to this user
    valid_device_id = any(device.get(constants.DEVICE_ID) == encoded_device_id for device in tv_data)

    if not valid_device_id:
        error_message = 'Invalid device id={}'.format(encoded_device_id)
        raise SpacebridgeApiRequestError(error_message, status_code=http.BAD_REQUEST)

    # construct parameters for subscription creation / updating
    ttl_seconds = client_subscription_message.clientSubscribeRequest.ttlSeconds
    expiration_time = get_expiration_timestamp_str(ttl_seconds=ttl_seconds)
    now = get_current_timestamp_str()
    params = {
        constants.TTL_SECONDS: str(ttl_seconds),
        constants.DEVICE_ID: encoded_device_id,
        constants.EXPIRED_TIME: expiration_time,
        constants.USER: request_context.current_user,
        constants.LAST_UPDATE_TIME: now,
        constants.SUBSCRIPTION_TYPE: constants.DRONE_MODE_TV
    }


    # delete existing subscriptions
    query = {
        constants.QUERY: json.dumps({
            constants.DEVICE_ID: encoded_device_id,
            constants.USER: request_context.current_user,
            constants.SUBSCRIPTION_TYPE: constants.DRONE_MODE_TV
        })
    }
    delete_response = yield async_kvstore_client.async_kvstore_delete_request(
        collection=constants.SUBSCRIPTIONS_COLLECTION_NAME,
        params=query,
        owner=constants.NOBODY,
        auth_header=request_context.auth_header)

    yield check_and_raise_error(delete_response, request_context, 'Delete existing tv subscriptions')
    # create subscription
    subscription_id = yield write_drone_mode_subscription(request_context,
                                                          params,
                                                          async_client_factory)
    server_subscription_response.subscriptionId = subscription_id
    server_subscription_response.serverSubscribeResponse.droneModeTVSubscribe.deviceId = device_id
    LOGGER.debug('Successfully wrote drone mode tv subscription with id=%s', subscription_id)

@defer.inlineCallbacks
def process_subscribe_drone_mode_ipad(request_context,
                                      client_subscription_message,
                                      server_subscription_response,
                                      async_client_factory):
    """
    Process subscribe to drone mode ipad events for a device id

    :param request_context: Used to authenticate kvstore requests
    :param client_single_request: client request object protobuf
    :param single_server_response: server response object protobuf
    :param async_client factory: factory class used to generate kvstore and spacebridge clients
    """

    LOGGER.debug('start of subscribe drone mode ipad')
    async_kvstore_client = async_client_factory.kvstore_client()

    LOGGER.debug('request_context=%s', request_context)
    # base64 encode device id
    device_id = request_context.device_id
    urlsafe_b64encoded_device_id = b64_to_urlsafe_b64(device_id)
    query = {
        constants.QUERY: json.dumps({
            constants.DEVICE_ID: device_id,
        }),
        constants.LIMIT: 1
    }

    # fetch device from registered_devices_table to get device name
    response = yield async_kvstore_client.async_kvstore_get_request(
        collection=constants.REGISTERED_DEVICES_COLLECTION_NAME,
        params=query,
        owner=request_context.current_user,
        auth_header=request_context.auth_header)

    yield check_and_raise_error(response, request_context, 'Fetch registered devices')

    device = yield response.json()
    if device:
        device = device[0]
    else:
        raise SpacebridgeApiRequestError('Invalid device id={}'.format(device_id), status_code=http.BAD_REQUEST)
    device_name = device[constants.DEVICE_NAME]

    # write to ipads collection
    ipad_json = {constants.DEVICE_NAME: device_name}
    response = yield async_kvstore_client.async_kvstore_post_or_update_request(
        constants.DRONE_MODE_IPADS_COLLECTION_NAME,
        json.dumps(ipad_json),
        request_context.system_auth_header,
        key_id=urlsafe_b64encoded_device_id,
        owner=request_context.current_user)

    # construct parameters for subscription creation / updating
    ttl_seconds = client_subscription_message.clientSubscribeRequest.ttlSeconds
    expiration_time = get_expiration_timestamp_str(ttl_seconds=ttl_seconds)
    now = get_current_timestamp_str()
    params = {
        constants.TTL_SECONDS: str(ttl_seconds),
        constants.DEVICE_ID: device_id,
        constants.LAST_UPDATE_TIME: now,
        constants.EXPIRED_TIME: expiration_time,
        constants.USER: request_context.current_user,
        constants.SUBSCRIPTION_TYPE: constants.DRONE_MODE_IPAD
    }
    # delete existing subscriptions
    query = {
        constants.QUERY: json.dumps({
            constants.DEVICE_ID: device_id,
            constants.USER: request_context.current_user,
            constants.SUBSCRIPTION_TYPE: constants.DRONE_MODE_IPAD
        })
    }
    delete_response = yield async_kvstore_client.async_kvstore_delete_request(
        collection=constants.SUBSCRIPTIONS_COLLECTION_NAME,
        params=query,
        owner=constants.NOBODY,
        auth_header=request_context.auth_header)
    yield check_and_raise_error(delete_response, request_context, 'Delete existing ipad subscriptions')

    # create subscription
    subscription_id = yield write_drone_mode_subscription(request_context,
                                                          params,
                                                          async_client_factory)
    server_subscription_response.subscriptionId = subscription_id
    server_subscription_response.serverSubscribeResponse.droneModeiPadSubscribe.SetInParent()
    LOGGER.debug('Successfully wrote drone mode ipad subscription with id=%s', subscription_id)

@defer.inlineCallbacks
def write_drone_mode_subscription(request_context, params, async_client_factory):
    """
    Method to write a kvstore drone mode subcription for a device id
    :param request_context: request context used to make kvstore request
    :param params: arguments used to create Subscription data object
    :param async_kvstore_client: kvstore client used to fetch data
    :return:
    """
    async_kvstore_client = async_client_factory.kvstore_client()
    subscription = Subscription(**params)
    LOGGER.debug('Subscription params=%s', params)
    data = subscription.to_json()

    # create subscription and return _key
    response = yield async_kvstore_client.async_kvstore_post_request(
        collection=constants.SUBSCRIPTIONS_COLLECTION_NAME,
        data=data,
        owner=constants.NOBODY,
        auth_header=request_context.auth_header)

    if response.code in {http.OK, http.CREATED}:
        response_json = yield response.json()
        subscription_id = response_json.get(constants.KEY)
        LOGGER.debug("Subscription Created. subscription_id=%s, expiration_time=%s",
                     subscription_id, subscription.expired_time)
        yield create_subscription_credentials(request_context, subscription_id, async_client_factory)
        defer.returnValue(subscription_id)

    error = yield response.text()
    error_message = "Failed to create Subscription. status_code={}, error={}".format(
        response.code, error)
    raise SpacebridgeApiRequestError(error_message, status_code=response.code)
