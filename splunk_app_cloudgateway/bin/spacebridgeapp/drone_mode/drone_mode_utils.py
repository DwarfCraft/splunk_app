"""
(C) 2020 Splunk Inc. All rights reserved.

Module which handles updating the device role mapping kvstore table
"""

import json
import sys
import os
from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'lib']))
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
from twisted.internet import defer
from twisted.python.failure import Failure
from twisted.web import http
from spacebridgeapp.rest.services.kvstore_service import KVStoreCollectionAccessObject as KvStore
from spacebridgeapp.rest.services.splunk_service import get_all_users
from spacebridgeapp.util import constants
from spacebridgeapp.util.error_utils import check_and_raise_error
from spacebridgeapp.util.kvstore import build_containedin_clause
from spacebridgeapp.util.py23 import b64_to_urlsafe_b64, urlsafe_b64_to_b64
from spacebridgeapp.logging import setup_logging

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + '_drone_mode_utils.log', 'drone_mode_utils')


@defer.inlineCallbacks
def get_registered_tvs(auth_header, user, async_kvstore_client, device_ids=None):
    """
    fetch list of apple tvs for the current user
    """

    LOGGER.debug('Getting registered tvs with device_ids=%s user=%s', device_ids, user)
    devices_table = constants.REGISTERED_DEVICES_COLLECTION_NAME
    try:
        registered_devices = []

        # optionally filter by device ids
        params = None
        query = {constants.REGISTERED_DEVICES_DEVICE_TYPE: constants.APPLE_TV}
        if device_ids:
            query = build_containedin_clause(constants.DEVICE_ID, device_ids)


        LOGGER.debug('get drone mode tvs query=%s', query)
        params = {constants.QUERY: json.dumps(query)}
        response = yield async_kvstore_client.async_kvstore_get_request(devices_table,
                                                                        owner=user,
                                                                        auth_header=auth_header,
                                                                        params=params)
        registered_devices = yield response.json() if response.code == http.OK else []

        LOGGER.debug('get_registered_tvs returned=%s', registered_devices)
        defer.returnValue(registered_devices)

    except Exception:
        LOGGER.exception('Exception getting registered_devices')
        defer.returnValue([])

@defer.inlineCallbacks
def get_registered_ipads(auth_header, user, async_kvstore_client, device_ids=None):
    """
    fetch list of apple ipads for the current user
    """

    LOGGER.debug('Getting registered ipads with device_ids=%s user=%s', device_ids, user)
    devices_table = constants.REGISTERED_DEVICES_COLLECTION_NAME
    try:
        registered_devices = []
        ipad_app_ids = [constants.IPAD_APP_ID_DEV, constants.IPAD_APP_ID_PROD]
        query = build_containedin_clause(constants.APP_ID, ipad_app_ids)
        # optionally filter by device ids
        if device_ids:
            query = {
                constants.AND_OPERATOR: [
                    query,
                    build_containedin_clause(constants.DEVICE_ID, device_ids)
                ]
            }

        LOGGER.debug('get drone mode ipads query=%s', query)
        params = {constants.QUERY: json.dumps(query)}
        response = yield async_kvstore_client.async_kvstore_get_request(devices_table,
                                                                        owner=user,
                                                                        auth_header=auth_header,
                                                                        params=params)
        registered_devices = yield response.json() if response.code == http.OK else []

        LOGGER.debug('get_registered_ipads returned=%s', registered_devices)
        defer.returnValue(registered_devices)

    except Exception:
        LOGGER.exception('Exception getting registered_devices')
        defer.returnValue([])

@defer.inlineCallbacks
def get_drone_mode_tvs(request_context, async_kvstore_client, user=None, device_ids=None):
    """Fetch list of tvs from the drone_mode_tvs collection"""

    params = None
    if not user:
        user = request_context.current_user

    if device_ids:
        urlsafe_device_ids = [b64_to_urlsafe_b64(device_id) for device_id in device_ids]
        query = build_containedin_clause(constants.KEY, urlsafe_device_ids)

        params = {constants.QUERY: json.dumps(query)}

    response = yield async_kvstore_client.async_kvstore_get_request(
        collection=constants.DRONE_MODE_TVS_COLLECTION_NAME,
        params=params,
        owner=user,
        auth_header=request_context.system_auth_header)

    yield check_and_raise_error(response, request_context, 'Get Drone Mode TVs')
    tvs = yield response.json()

    LOGGER.debug('get_drone_mode_tvs returned=%s', tvs)
    defer.returnValue(tvs)

def has_grid(obj, is_json=False):
    """
    Returns true if the proto (or optionally_json)  has a grid value
    :param proto:
    """
    if is_json:
        try:
            # this is the case where we're in a pure dict
            tv_grid = obj.get(constants.TV_GRID)
        except:
            # Thi is the case where we're in the data object
            tv_grid = obj.tv_grid

        return not is_empty_grid(tv_grid)
    else:
        tv_grid = obj.tv_grid
        if tv_grid and tv_grid.width != 0 or tv_grid.height != 0 or tv_grid.position != 0 or tv_grid.device_ids:
            return True
        return False

def is_empty_grid(tv_grid):
    """
    Returns True if the data structure is an empty grid
    """
    return not (tv_grid and (tv_grid.get(constants.HEIGHT) != 0 or
                             tv_grid.get(constants.WIDTH) != 0 or
                             tv_grid.get(constants.POSITION) != 0 or
                             tv_grid.get(constants.DEVICE_IDS)))

@defer.inlineCallbacks
def get_drone_mode_users(async_client_factory, auth_header):
    """
    Retrieve users who have registered a drone mode ipad
    :param async_client_factory: used to generate splunk client and kvstore client
                                 used in order to make requests for users/devices
    :param auth_header: used to authenticate client requests
    """
    async_splunk_client = async_client_factory.splunk_client()
    async_kvstore_client = async_client_factory.kvstore_client()
    response_code, all_users = yield async_splunk_client.async_get_all_users(auth_header)
    users = []

    if response_code == http.OK:
        requests = []
        for user in all_users:
            request = get_registered_ipads(auth_header, user, async_kvstore_client)
            requests.append(request)

        users = []
        exceptions = []
        responses = yield defer.DeferredList(requests, consumeErrors=True)
        for response in responses:
            if isinstance(response[1], Failure):
                exceptions.append(response[1])
            else:
                (_, ipads) = response
                if ipads and ipads[0][constants.USER_KEY]:
                    users.append(ipads[0][constants.USER_KEY])
        if exceptions:
            LOGGER.error('Encountered exceptions fetching drone mode tv data: e=%s', exceptions)

    result_tuple = (response_code, users)
    LOGGER.debug('get_drone_mode_users returned=%s', result_tuple)
    defer.returnValue(result_tuple)

@defer.inlineCallbacks
def clean_up_orphaned_configs(request_context,
                              async_kvstore_client):
    """
    This function is to clean up configs that are tied to unregistered devices
    :param request_context: Request context used to make kvstore requests
    :param async_kvstore_client: Kvstore client used to make kvstore requests
    """
    users = get_all_users(request_context.system_auth_header.session_token)
    requests = []
    for user in users:
        drone_mode_tvs = yield get_drone_mode_tvs(request_context,
                                                  async_kvstore_client,
                                                  user=user)
        if drone_mode_tvs:
            registered_tv_list = yield get_registered_tvs(request_context.auth_header,
                                                          user,
                                                          async_kvstore_client)

            registered_device_ids = {device[constants.DEVICE_ID] for device in registered_tv_list}
            tv_config_ids_to_delete = [config[constants.KEY] for config in drone_mode_tvs if urlsafe_b64_to_b64(config[constants.KEY]) not in registered_device_ids]
            if tv_config_ids_to_delete:
                LOGGER.debug('orphaned tv config ids to delete for user=%s ids=%s', user, tv_config_ids_to_delete)
                query = build_containedin_clause(constants.KEY, tv_config_ids_to_delete)
                params = {constants.QUERY: json.dumps(query)}
                request = async_kvstore_client.async_kvstore_delete_request(collection=constants.DRONE_MODE_TVS_COLLECTION_NAME,
                                                                            auth_header=request_context.system_auth_header,
                                                                            owner=user,
                                                                            params=params)
                requests.append(request)

    exceptions = []
    responses = yield defer.DeferredList(requests, consumeErrors=True)
    for response in responses:
        LOGGER.debug('response=%s', response)
        if isinstance(response[1], Failure):
            exceptions.append(response[1])
    if exceptions:
        LOGGER.error('Encountered exceptions deleting drone mode tv configs: e=%s', exceptions)

