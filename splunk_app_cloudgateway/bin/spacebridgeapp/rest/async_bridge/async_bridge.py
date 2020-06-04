"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for accessing async and reactor based methods
"""
import sys
from threading import Thread

from splunk.persistconn.application import PersistentServerConnectionApplication
from splunk.clilib.bundle_paths import make_splunkhome_path
import splunk.rest as rest
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from twisted.web import http
from twisted.internet import reactor
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.rest.base_endpoint import BaseRestHandler
from spacebridgeapp.ar.permissions.async_permissions_client import AsyncArPermissionsClient
from spacebridgeapp.rest.clients.async_client_factory import AsyncClientFactory
from spacebridgeapp.rest.async_bridge.async_bridge_requests import dashboard_list_request, \
                                                                   get_app_list_request, \
                                                                   post_app_list_request, get_all_apps_request, \
                                                                   get_tv_request, post_tv_config_request, post_tv_bookmark_request, \
                                                                   get_tv_bookmark_request, delete_tv_bookmark_request, \
                                                                   activate_tv_bookmark_request, delete_tv_config_request, \
                                                                   drone_mode_tv_subscribe_request, mpc_broadcast_request, \
                                                                   tv_interaction_request, tv_captain_url_request, \
                                                                   drone_mode_ipad_subscribe_request, post_tv_config_bulk_request
from spacebridgeapp.messages.request_context import RequestContext

from cloudgateway.private.util.splunk_auth_header import SplunkAuthHeader
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, AUTHTOKEN, SESSION, QUERY, USER

REQUEST_TYPE = 'request_type'
PERMISSION = 'permission'
ID = 'id'
IDS = 'ids'
OBJECT_TYPE = 'object_type'
ROLES = 'roles'
DASHBOARD_LIST_REQUEST = 'dashboard_list'
APP_LIST_REQUEST = 'app_list'
ALL_APPS_REQUEST = 'all_apps'
TV_LIST_REQUEST = 'tv_list'
TV_CONFIG_REQUEST = 'tv_config'
TV_CONFIG_BULK_REQUEST = 'tv_config_bulk'
TV_BOOKMARK_REQUEST = 'tv_bookmark'
ACTIVATE_TV_BOOKMARK_REQUEST = 'activate_tv_bookmark'
DRONE_MODE_TV_SUBSCRIBE_REQUEST = 'drone_mode_tv_subscribe'
DRONE_MODE_IPAD_SUBSCRIBE_REQUEST = 'drone_mode_ipad_subscribe'
MPC_BROADCAST_REQUEST = 'mpc_broadcast'
TV_INTERACTION_REQUEST = 'tv_interaction'
TV_CAPTAIN_URL_REQUEST = 'captain_url'
SUBSCRIPTION_PING = 'subscription_ping'

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + ".log", "rest_async_bridge")
VALID_GET_REQUESTS = {DASHBOARD_LIST_REQUEST, APP_LIST_REQUEST, ALL_APPS_REQUEST, TV_LIST_REQUEST, TV_BOOKMARK_REQUEST}
VALID_POST_REQUESTS = {APP_LIST_REQUEST,
                       TV_CONFIG_REQUEST,
                       TV_CONFIG_BULK_REQUEST,
                       TV_BOOKMARK_REQUEST,
                       ACTIVATE_TV_BOOKMARK_REQUEST,
                       DRONE_MODE_TV_SUBSCRIBE_REQUEST,
                       DRONE_MODE_IPAD_SUBSCRIBE_REQUEST,
                       MPC_BROADCAST_REQUEST,
                       TV_INTERACTION_REQUEST,
                       TV_CAPTAIN_URL_REQUEST,
                       SUBSCRIPTION_PING
                      }
VALID_DELETE_REQUESTS = {TV_BOOKMARK_REQUEST, TV_CONFIG_REQUEST}

class AsyncBridge(BaseRestHandler, PersistentServerConnectionApplication):
    """
    Main class for handling the async_bridge endpoint. Subclasses the spacebridge_app
    BaseRestHandler.

    """

    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)
        Thread(target=reactor.run, args=(False,)).start()
        self.uri = rest.makeSplunkdUri()
        self.async_client_factory = AsyncClientFactory(self.uri)
        self.async_kvstore_client = self.async_client_factory.kvstore_client()

    def get(self, request):
        """
        Handler which passes off requests to the relevant GET handler
        """

        request_type = request[QUERY].get(REQUEST_TYPE)

        if request_type not in VALID_GET_REQUESTS:
            return {
                'payload': 'No request_type supplied',
                'status': http.BAD_REQUEST,
            }

        authtoken = request[SESSION][AUTHTOKEN]
        user = request[SESSION][USER]
        auth_header = SplunkAuthHeader(authtoken)

        request_context = RequestContext(auth_header, current_user=user, system_auth_header=auth_header)

        if request_type == DASHBOARD_LIST_REQUEST:
            response = dashboard_list_request(request, self.async_client_factory, request_context)

        elif request_type == APP_LIST_REQUEST:
            response = get_app_list_request(request, self.async_client_factory, request_context)

        elif request_type == ALL_APPS_REQUEST:
            response = get_all_apps_request(request, self.async_client_factory, request_context)

        elif request_type == TV_LIST_REQUEST:
            response = get_tv_request(request, self.async_kvstore_client, request_context)

        elif request_type == TV_BOOKMARK_REQUEST:
            response = get_tv_bookmark_request(request, self.async_kvstore_client, request_context)

        status = http.OK
        if 'error' in response:
            status = http.INTERNAL_SERVER_ERROR
        return {
            'payload': response,
            'status': status,
        }

    def post(self, request):
        """
        Handler which passes off requests to the relevant POST handler
        """
        authtoken = request[SESSION][AUTHTOKEN]
        request_type = request[QUERY].get(REQUEST_TYPE)
        user = request[SESSION][USER]
        auth_header = SplunkAuthHeader(authtoken)
        system_auth_header = auth_header
        request_context = RequestContext(auth_header, current_user=user, system_auth_header=system_auth_header)

        if request_type not in VALID_POST_REQUESTS:
            return {
                'payload': 'No request_type supplied',
                'status': http.BAD_REQUEST,
            }

        if request_type == APP_LIST_REQUEST:
            response = post_app_list_request(request, self.async_client_factory, request_context)

        elif request_type == TV_CONFIG_REQUEST:
            response = post_tv_config_request(request, self.async_client_factory, request_context)

        elif request_type == TV_CONFIG_BULK_REQUEST:
            response = post_tv_config_bulk_request(request, self.async_client_factory, request_context)

        elif request_type == TV_BOOKMARK_REQUEST:
            response = post_tv_bookmark_request(request, self.async_kvstore_client, request_context)

        elif request_type == ACTIVATE_TV_BOOKMARK_REQUEST:
            response = activate_tv_bookmark_request(request, self.async_client_factory, request_context)

        elif request_type == DRONE_MODE_IPAD_SUBSCRIBE_REQUEST:
            response = drone_mode_ipad_subscribe_request(request, self.async_client_factory, request_context)

        elif request_type == DRONE_MODE_TV_SUBSCRIBE_REQUEST:
            response = drone_mode_tv_subscribe_request(request, self.async_client_factory, request_context)

        elif request_type == MPC_BROADCAST_REQUEST:
            response = mpc_broadcast_request(request, self.async_client_factory, request_context)

        elif request_type == TV_INTERACTION_REQUEST:
            response = tv_interaction_request(request, self.async_client_factory, request_context)

        elif request_type == TV_CAPTAIN_URL_REQUEST:
            response = tv_captain_url_request(request, self.async_client_factory, request_context)

        elif request_type == SUBSCRIPTION_PING:
            response = subscription_ping(request, self.async_client_factory, request_context)




        status = http.OK
        if 'error' in response:
            status = http.INTERNAL_SERVER_ERROR

        return {
            'payload': response,
            'status': status,
        }

    def delete(self, request):
        """
        Handler which passes off requests to the relevant DELETE handler
        """
        authtoken = request[SESSION][AUTHTOKEN]
        request_type = request[QUERY].get(REQUEST_TYPE)
        user = request[SESSION][USER]
        auth_header = SplunkAuthHeader(authtoken)
        system_auth_header = auth_header
        request_context = RequestContext(auth_header, current_user=user, system_auth_header=system_auth_header)

        if request_type not in VALID_DELETE_REQUESTS:
            return {
                'payload': 'Invalid request_type supplied or request_type not present',
                'status': http.BAD_REQUEST,
            }

        if request_type == TV_BOOKMARK_REQUEST:
            response = delete_tv_bookmark_request(request, self.async_kvstore_client, request_context)

        elif request_type == TV_CONFIG_REQUEST:
            response = delete_tv_config_request(request, self.async_client_factory, request_context)

        status = http.OK
        if 'error' in response:
            status = http.INTERNAL_SERVER_ERROR

        return {
            'payload': response,
            'status': status,
        }

