"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for accessing and setting app_list kvstore records
"""

import sys
import json
from urllib2 import unquote
from urlparse import parse_qsl

from splunk.persistconn.application import PersistentServerConnectionApplication
from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23


from twisted.web import http
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.rest.util import errors as Errors
from spacebridgeapp.rest.base_endpoint import BaseRestHandler
from spacebridgeapp.rest.services.splunk_service import get_app_list_request
from spacebridgeapp.rest.services.kvstore_service import KVStoreCollectionAccessObject as KvStore
from spacebridgeapp.util.constants import USER_META_COLLECTION_NAME, SPACEBRIDGE_APP_NAME, AUTHTOKEN, \
                                          SESSION, USER, DASHBOARD_APP_LIST, APP_LIST, APP_NAMES, KEY


LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + ".log", "rest_app_list")


class AppList(BaseRestHandler, PersistentServerConnectionApplication):
    """
    Main class for handling the app_list endpoint. Subclasses the spacebridge_app
    BaseRestHandler.

    """

    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)

    def get(self, request):
        """
        Handler which retrieves kvstore app_list data for the current user
        """

        stored_app_list = get_app_list(request)

        app_name_dict = get_app_dict(request)
        payload = {
            APP_LIST: [(elem, app_name_dict[elem])
                       for elem in stored_app_list
                       if elem in app_name_dict],
        }

        return {
            'payload': payload,
            'status': http.OK,
        }

    def post(self, request):
        """
        Handler which creates a new app_list data entry in kvstore for the
        current user
        """
        # Check payload is valid
        # create kvstore entry
        app_list = validate_write_request(request)
        params = {KEY: DASHBOARD_APP_LIST,
                  APP_NAMES: app_list}

        kvstore = KvStore(USER_META_COLLECTION_NAME, request[SESSION][AUTHTOKEN], owner=request[SESSION][USER])
        try:
            kvstore.insert_or_update_item_containing_key(params)
            return {
                'payload': 'Successfully wrote app_list={} for user={}'.format(app_list, request[SESSION][USER]),
                'status': http.OK,
            }

        except Exception as e:
            raise Errors.SpacebridgeRestError('Error: failed to write kvstore entry with id={}'.format(DASHBOARD_APP_LIST), 400)


    def put(self, request):
        """
        Handler which updates app_list data entry in kvstore for the
        current user
        """
        # Check payload is valid
        # update kvstore entry
        app_list = validate_write_request(request)
        params = {KEY: DASHBOARD_APP_LIST,
                  APP_NAMES: app_list}

        kvstore = KvStore(USER_META_COLLECTION_NAME, request[SESSION][AUTHTOKEN], owner=request[SESSION][USER])
        try:
            kvstore.update_item_by_key(DASHBOARD_APP_LIST, params)
            return {
                'payload': 'Successfully updated kvstore entry with id={}'.format(DASHBOARD_APP_LIST),
                'status': http.OK,
            }
        except Exception as e:
            raise Errors.SpacebridgeRestError('Error: failed to update kvstore entry with id={}'.format(DASHBOARD_APP_LIST), 400)

def validate_write_request(request):
    """
    Common validation for put and post
    methods

    :param request: The HTTP request
    :return app_list: The app list to write to kvstore
    """

    params = {k:unquote(v) for k, v in dict(parse_qsl(request['payload'])).iteritems()}
    app_list = params.get(APP_LIST)
    if app_list is None:
        raise Errors.SpacebridgeRestError('Error: Put request must have an app_list', 400)

    jsonified_app_list = json.loads(app_list)
    invalid_app_list = invalid_apps(request, jsonified_app_list)

    if invalid_app_list:
        raise Errors.SpacebridgeRestError('Error: Could not find app(s)={}'.format(invalid_app_list), 400)

    return app_list


def invalid_apps(request, app_list):
    """
    tests if any apps in an app list
    are invalid based on the viewable apps using
    the permissions of the authtoken from the supplied request

    :param request: The HTTP request
    :param app_list: The app list being tested
    :return invalid_apps: The list of invalid apps
    """

    app_name_dict = get_app_dict(request)
    invalid_app_list = [app for app in app_list if app not in app_name_dict]
    return invalid_app_list


def get_app_list(request):
    """
    Returns a json object containing the app_list data

    :param request: The http request
    :return: json app list data
    """
    try:
        kvstore = KvStore(USER_META_COLLECTION_NAME, request[SESSION][AUTHTOKEN], owner=request[SESSION][USER])
        r, entry = kvstore.get_item_by_key(DASHBOARD_APP_LIST)
        entry = json.loads(entry)
        app_names = json.loads(entry[APP_NAMES])
        if app_names is None:
            app_names = []
    except Exception as e:
        LOGGER.exception('get_app_list failed')
        app_names = []

    return app_names

