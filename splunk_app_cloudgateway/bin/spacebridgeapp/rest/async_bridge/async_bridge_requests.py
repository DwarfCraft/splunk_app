"""
(C) 2019 Splunk Inc. All rights reserved.

Module containing functions called by the async bridge rest handler
"""
import json
import base64
import sys, os
from google.protobuf.json_format import MessageToJson
from twisted.internet import defer
from splapp_protocol import request_pb2, subscription_pb2
from spacebridgeapp.rest.async_bridge.utils import get_app_dict, make_callable_from_sync, validate_write_request
from spacebridgeapp.request.dashboard_request_processor import process_dashboard_list_request
from spacebridgeapp.request.app_list_request_processor import process_dashboard_app_list_get_request, \
                                                              process_dashboard_app_list_set_request, \
                                                              fetch_app_names
from spacebridgeapp.request.drone_mode_request_processor import process_tv_get_request, process_tv_config_set_request, \
                                                                process_tv_bookmark_set_request, process_tv_bookmark_get_request, \
                                                                process_tv_bookmark_delete_request, process_tv_bookmark_activate_request,\
                                                                process_tv_config_delete_request, process_mpc_broadcast_request, \
                                                                process_tv_interaction_request, process_tv_captain_url_request, \
                                                                process_subscribe_drone_mode_tv, process_subscribe_drone_mode_ipad, \
                                                                process_tv_config_bulk_set_request

from spacebridgeapp.util.constants import QUERY, DASHBOARD_IDS, MINIMAL_LIST, MAX_RESULTS, OFFSET
from spacebridgeapp.util import constants
from spacebridgeapp.drone_mode.data.drone_mode_data import TVConfig

REQUEST_TYPE = 'request_type'
PERMISSION = 'permission'
ID = 'id'
IDS = 'ids'
OBJECT_TYPE = 'object_type'
ROLES = 'roles'
APP_LIST = 'app_list'


@make_callable_from_sync
@defer.inlineCallbacks
def dashboard_list_request(request, async_client_factory, request_context):
    """
    REST handler to fetch a list of dashboards
    """

    try:
        offset = request[QUERY].get(OFFSET)
        max_results = request[QUERY].get(MAX_RESULTS)
        dashboard_ids = request[QUERY].get(DASHBOARD_IDS)
        minimal_list = int(request[QUERY].get(MINIMAL_LIST, 0))

        client_request_proto = request_pb2.ClientSingleRequest()
        dashboard_request = client_request_proto.dashboardListRequest
        if dashboard_ids:
            dashboard_ids = [dashboard_ids] if not isinstance(dashboard_ids, list) else dashboard_ids
            dashboard_request.dashboardIds.extend(dashboard_ids)
        if offset:
            dashboard_request.offset = int(offset)
        if max_results:
            dashboard_request.maxResults = int(max_results)
        dashboard_request.minimalList = minimal_list

        server_response_proto = request_pb2.ServerSingleResponse()

        yield process_dashboard_list_request(request_context,
                                             client_request_proto,
                                             server_response_proto,
                                             async_client_factory)

        defer.returnValue(json.loads(MessageToJson(server_response_proto)))

    except Exception as e:
        defer.returnValue({'error': e.message})


@make_callable_from_sync
@defer.inlineCallbacks
def get_app_list_request(request, async_client_factory, request_context):
    """
    REST handler to fetch the selected app list for the current user
    """

    try:
        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()

        selected_apps = yield process_dashboard_app_list_get_request(request_context,
                                                                     client_request_proto,
                                                                     server_response_proto,
                                                                     async_client_factory)

        splunk_client = async_client_factory.splunk_client()
        app_list = yield fetch_app_names(request_context, splunk_client)
        app_dict = get_app_dict(app_list)
        # This filters out apps that are invalid from displaying in the app selection tab
        defer.returnValue({'app_list': [{'app_name': app, 'display_app_name': app_dict[app]} for app in selected_apps if app in app_dict]})

    except Exception as e:
        defer.returnValue({'error': e.message})


@make_callable_from_sync
@defer.inlineCallbacks
def get_all_apps_request(request, async_client_factory, request_context):
    """
    REST handler to fetch all apps visible to current user
    """

    try:
        splunk_client = async_client_factory.splunk_client()
        app_list = yield fetch_app_names(request_context, splunk_client)
        defer.returnValue([{'app_name': app.app_name, 'display_app_name': app.display_app_name} for app in app_list])

    except Exception as e:
        defer.returnValue({'error': e.message})


@make_callable_from_sync
@defer.inlineCallbacks
def post_app_list_request(request, async_client_factory, request_context):
    """
    Update app list selection for current user
    """

    try:
        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()
        app_list_request = client_request_proto.dashboardAppListSetRequest
        splunk_client = async_client_factory.splunk_client()
        total_app_list = yield fetch_app_names(request_context, splunk_client)
        app_list = validate_write_request(request, total_app_list)
        app_list_request.appNames.extend(json.loads(app_list))

        success = yield process_dashboard_app_list_set_request(request_context,
                                             client_request_proto,
                                             server_response_proto,
                                             async_client_factory)

        defer.returnValue(json.loads(MessageToJson(server_response_proto)))

    except Exception as e:
        defer.returnValue({'error': e.message})

@make_callable_from_sync
@defer.inlineCallbacks
def get_tv_request(request, async_kvstore_client, request_context):
    """
    Retrieve either a list or a singular TVData instance
    """
    try:
        device_id = request[constants.QUERY].get(constants.DEVICE_ID)
        client_request_proto = request_pb2.ClientSingleRequest()
        tv_get_request = client_request_proto.tvGetRequest
        if device_id:
            tv_get_request.deviceId = device_id
        server_response_proto = request_pb2.ServerSingleResponse()
        result = yield process_tv_get_request(request_context,
                                              client_request_proto,
                                              server_response_proto,
                                              async_kvstore_client)
        defer.returnValue(json.loads(MessageToJson(server_response_proto, including_default_value_fields=True)))
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        #print(exc_type, fname, exc_tb.tb_lineno)
        defer.returnValue('{} {} {} {}'.format(e.message, exc_type, fname, exc_tb.tb_lineno))
        #defer.returnValue({'error': e.message})

@make_callable_from_sync
@defer.inlineCallbacks
def post_tv_config_request(request, async_client_factory, request_context):
    """
    Set a TV config
    """
    try:
        body = json.loads(request[constants.PAYLOAD])
        device_id = body.get(constants.DEVICE_ID, '')
        device_name = body.get(constants.DEVICE_NAME, '')
        mode = int(body.get(constants.MODE, constants.UNKNOWN_MODE))
        tv_grid = body.get(constants.TV_GRID)
        content = body.get(constants.CONTENT, '')
        timestamp = body.get(constants.TIMESTAMP, 0)
        captain_id = body.get(constants.CAPTAIN_ID, '')
        captain_url = body.get(constants.CAPTAIN_URL, '')
        input_tokens = body.get('input_tokens')
        user_choices = body.get('user_choices')
        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()

        tv_config = TVConfig(device_id=device_id,
                device_name=device_name,
                mode=mode,
                content=content,
                tv_grid=tv_grid,
                timestamp=timestamp,
                captain_id=captain_id,
                captain_url=captain_url,
                user_choices=user_choices,
                input_tokens=input_tokens)
        tv_config_proto = client_request_proto.tvConfigSetRequest.tvConfig
        tv_config.set_protobuf(tv_config_proto)
        result = yield process_tv_config_set_request(request_context,
                                           client_request_proto,
                                           server_response_proto,
                                           async_client_factory)

        #defer.returnValue(result)
        defer.returnValue(json.loads(MessageToJson(server_response_proto)))

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        #print(exc_type, fname, exc_tb.tb_lineno)
        defer.returnValue('{} {} {} {}'.format(e.message, exc_type, fname, exc_tb.tb_lineno))

@make_callable_from_sync
@defer.inlineCallbacks
def post_tv_config_bulk_request(request, async_client_factory, request_context):
    """
    Set bulk tv config
    """
    try:
        body = json.loads(request[constants.PAYLOAD])
        tv_list = body.get('tv_config_list', [])

        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()

        proto_array = [TVConfig(**tv).to_protobuf() for tv in tv_list]
        client_request_proto.tvConfigBulkSetRequest.tvConfig.extend(proto_array)
        result = yield process_tv_config_bulk_set_request(request_context,
                                           client_request_proto,
                                           server_response_proto,
                                           async_client_factory)
    except Exception as e:
        defer.returnValue({'error': e.message})


@make_callable_from_sync
@defer.inlineCallbacks
def post_tv_bookmark_request(request, async_kvstore_client, request_context):
    """
    Set a TV Bookmark
    """
    try:
        body = json.loads(request[constants.PAYLOAD])
        description = body.get(constants.BOOKMARK_DESCRIPTION, '')
        name = body.get(constants.NAME, '')
        device_ids = body.get(constants.DEVICE_ID_LIST, [])
        overwrite = body.get('overwrite', False)

        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()


        request_proto = client_request_proto.tvBookmarkSetRequest
        request_proto.deviceIds.extend(device_ids)
        request_proto.description = description
        request_proto.name = name
        request_proto.overwrite = overwrite

        result = yield process_tv_bookmark_set_request(request_context,
                                           client_request_proto,
                                           server_response_proto,
                                           async_kvstore_client)

        defer.returnValue(json.loads(MessageToJson(server_response_proto)))


    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        #print(exc_type, fname, exc_tb.tb_lineno)
        defer.returnValue('{} {} {} {}'.format(e.message, exc_type, fname, exc_tb.tb_lineno))
        #defer.returnValue({'error': e.message})
        defer.returnValue({'error': e.message})

@make_callable_from_sync
@defer.inlineCallbacks
def get_tv_bookmark_request(request, async_kvstore_client, request_context):
    """
    Set a TV Bookmark
    """
    try:
        bookmark_name = request[constants.QUERY].get(constants.NAME)

        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()


        request_proto = client_request_proto.tvBookmarkGetRequest
        if bookmark_name:
            request_proto.bookmarkName = bookmark_name

        result = yield process_tv_bookmark_get_request(request_context,
                                           client_request_proto,
                                           server_response_proto,
                                           async_kvstore_client)

        #defer.returnValue(result)
        defer.returnValue(json.loads(MessageToJson(server_response_proto)))


    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        #print(exc_type, fname, exc_tb.tb_lineno)
        defer.returnValue('{} {} {} {}'.format(e.message, exc_type, fname, exc_tb.tb_lineno))
        #defer.returnValue({'error': e.message})
        defer.returnValue({'error': e.message})

@make_callable_from_sync
@defer.inlineCallbacks
def delete_tv_bookmark_request(request, async_kvstore_client, request_context):
    """
    Delete a TV bookmark
    """
    try:
        body = json.loads(request[constants.PAYLOAD])
        bookmark_name = body.get(constants.NAME)

        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()
        tv_bookmark_proto = client_request_proto.tvBookmarkDeleteRequest
        tv_bookmark_proto.bookmarkName = bookmark_name
        result = yield process_tv_bookmark_delete_request(request_context,
                                           client_request_proto,
                                           server_response_proto,
                                           async_kvstore_client)

        #defer.returnValue(result)
        defer.returnValue(json.loads(MessageToJson(server_response_proto)))

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        #print(exc_type, fname, exc_tb.tb_lineno)
        defer.returnValue('{} {} {} {}'.format(e.message, exc_type, fname, exc_tb.tb_lineno))
        #defer.returnValue({'error': e.message})
        defer.returnValue({'error': e.message})
        defer.returnValue({'error': e.message})

@make_callable_from_sync
@defer.inlineCallbacks
def activate_tv_bookmark_request(request, async_client_factory, request_context):
    """
    Activate a TV bookmark
    """
    try:
        body = json.loads(request[constants.PAYLOAD])
        bookmark_name = body.get(constants.NAME)

        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()

        tv_activate_bookmark_proto = client_request_proto.tvBookmarkActivateRequest
        tv_activate_bookmark_proto.bookmarkName = bookmark_name
        result = yield process_tv_bookmark_activate_request(request_context,
                                           client_request_proto,
                                           server_response_proto,
                                           async_client_factory)

        defer.returnValue(json.loads(MessageToJson(server_response_proto)))

    except Exception as e:
        defer.returnValue({'error': e.message})

@make_callable_from_sync
@defer.inlineCallbacks
def delete_tv_config_request(request, async_client_factory, request_context):
    """
    Delete a TV config
    """
    try:
        body = json.loads(request[constants.PAYLOAD])
        device_id = body.get(constants.DEVICE_ID, [])

        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()
        tv_config_proto = client_request_proto.tvConfigDeleteRequest
        tv_config_proto.deviceId.extend(device_id)
        result = yield process_tv_config_delete_request(request_context,
                                           client_request_proto,
                                           server_response_proto,
                                           async_client_factory)

        #defer.returnValue(result)
        defer.returnValue(json.loads(MessageToJson(server_response_proto)))

    except Exception as e:
        defer.returnValue({'error': e.message})

@make_callable_from_sync
@defer.inlineCallbacks
def drone_mode_tv_subscribe_request(request, async_client_factory, request_context):
    """
    Subscribe to a drone mode tv device
    """
    try:
        body = json.loads(request[constants.PAYLOAD])
        device_id = body.get(constants.DEVICE_ID)
        raw_device_id = str(base64.b64decode(device_id))
        ttl_seconds = body.get('ttl_seconds', 100)

        client_subscription_proto = subscription_pb2.ClientSubscriptionMessage()
        subscription_response_proto = subscription_pb2.ServerSubscriptionResponse()

        client_subscription_proto.clientSubscribeRequest.droneModeTVSubscribe.deviceId = raw_device_id
        client_subscription_proto.clientSubscribeRequest.ttlSeconds = ttl_seconds


        result = yield process_subscribe_drone_mode_tv(request_context,
                                           client_subscription_proto,
                                           subscription_response_proto,
                                           async_client_factory)

        #defer.returnValue(result)
        defer.returnValue(json.loads(MessageToJson(subscription_response_proto)))


    except Exception as e:
        defer.returnValue({'error': e.message})

@make_callable_from_sync
@defer.inlineCallbacks
def drone_mode_ipad_subscribe_request(request, async_client_factory, request_context):
    """
    Subscribe to a drone mode ipad device
    """
    try:
        body = json.loads(request[constants.PAYLOAD])
        ttl_seconds = body.get('ttl_seconds', 100)

        client_subscription_proto = subscription_pb2.ClientSubscriptionMessage()
        subscription_response_proto = subscription_pb2.ServerSubscriptionResponse()

        client_subscription_proto.clientSubscribeRequest.ttlSeconds = ttl_seconds

        device_id = 'Ku4XO7DSJruGsgSR/Z+Lop2Kc9iTGCTZDT5iuMuYrbo='
        raw_device_id = base64.b64decode(device_id)
        request_context.device_id = raw_device_id
        result = yield process_subscribe_drone_mode_ipad(request_context,
                                           client_subscription_proto,
                                           subscription_response_proto,
                                           async_client_factory)

        #defer.returnValue(result)
        defer.returnValue(json.loads(MessageToJson(subscription_response_proto)))


    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        #print(exc_type, fname, exc_tb.tb_lineno)
        defer.returnValue('{} {} {} {}'.format(e.message, exc_type, fname, exc_tb.tb_lineno))
        defer.returnValue({'error': e.message})


        defer.returnValue({'error': e.message})

@make_callable_from_sync
@defer.inlineCallbacks
def mpc_broadcast_request(request, async_client_factory, request_context):
    """
    Tell a device to start MPC broadcasting
    """
    try:
        body = json.loads(request[constants.PAYLOAD])
        device_id = body.get(constants.DEVICE_ID)
        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()
        broadcast_proto = client_request_proto.startMPCBroadcastRequest
        broadcast_proto.deviceId = device_id
        result = yield process_mpc_broadcast_request(request_context,
                                           client_request_proto,
                                           server_response_proto,
                                           async_client_factory)

        #defer.returnValue(result)
        defer.returnValue(json.loads(MessageToJson(server_response_proto)))




    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        #print(exc_type, fname, exc_tb.tb_lineno)
        defer.returnValue('{} {} {} {}'.format(e.message, exc_type, fname, exc_tb.tb_lineno))
        defer.returnValue({'error': e.message})

@make_callable_from_sync
@defer.inlineCallbacks
def tv_interaction_request(request, async_client_factory, request_context):
    """
    Send a tv interaction to a device
    """
    try:
        body = json.loads(request[constants.PAYLOAD])
        device_id = body.get(constants.DEVICE_ID)
        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()
        tv_interaction_request = client_request_proto.tvInteractionRequest
        tv_interaction_proto = tv_interaction_request.tvInteraction
        tv_interaction_proto.device_id = device_id
        if body.get('slideshow_go_to'):
            tv_interaction_proto.slideshow_go_to.SetInParent()
        elif body.get('slideshow_stop'):
            tv_interaction_proto.slideshow_stop.SetInParent()
        elif body.get('slideshow_forward'):
            tv_interaction_proto.slideshow_forward.SetInParent()
        elif body.get('slideshow_back'):
            tv_interaction_proto.slideshow_back.SetInParent()
        elif body.get('slideshow_speed'):
            tv_interaction_proto.slideshow_speed.speed = int(body.get('slideshow_speed'))
        else:
            raise ValueError('invalid params')

        result = yield process_tv_interaction_request(request_context,
                                           client_request_proto,
                                           server_response_proto,
                                           async_client_factory)

        #defer.returnValue(result)
        defer.returnValue(json.loads(MessageToJson(server_response_proto)))




    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        #print(exc_type, fname, exc_tb.tb_lineno)
        defer.returnValue('{} {} {} {}'.format(e.message, exc_type, fname, exc_tb.tb_lineno))
        defer.returnValue({'error': e.message})

@make_callable_from_sync
@defer.inlineCallbacks
def tv_captain_url_request(request, async_client_factory, request_context):
    """
    Send a tv interaction to a device
    """
    try:
        body = json.loads(request[constants.PAYLOAD])
        captain_id = body.get(constants.CAPTAIN_ID, '')
        captain_url = body.get(constants.CAPTAIN_URL, '')
        update_flag = body.get(constants.UPDATE_FLAG, False)
        timestamp = body.get(constants.TIMESTAMP, 0)

        client_request_proto = request_pb2.ClientSingleRequest()
        server_response_proto = request_pb2.ServerSingleResponse()

        captain_url_request = client_request_proto.tvCaptainUrlRequest
        captain_url_request.captainId = captain_id
        captain_url_request.captainUrl = captain_url
        captain_url_request.updateFlag = update_flag
        captain_url_request.timestamp = timestamp


        result = yield process_tv_captain_url_request(request_context,
                                           client_request_proto,
                                           server_response_proto,
                                           async_client_factory)

        #defer.returnValue(result)
        defer.returnValue(json.loads(MessageToJson(server_response_proto)))




    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        #print(exc_type, fname, exc_tb.tb_lineno)
        defer.returnValue('{} {} {} {}'.format(e.message, exc_type, fname, exc_tb.tb_lineno))
        defer.returnValue({'error': e.message})

