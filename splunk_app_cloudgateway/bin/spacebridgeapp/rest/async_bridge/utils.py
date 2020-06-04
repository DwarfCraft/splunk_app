"""
utils used within the async_bridge module
"""
import json
import sys
from twisted.internet import reactor, defer, threads
from spacebridgeapp.rest.util import errors as Errors
from spacebridgeapp.rest.services.kvstore_service import KVStoreCollectionAccessObject as KvStore
from spacebridgeapp.util.constants import APP_LIST

if sys.version_info < (3, 0):
    from urllib2 import unquote
    from urlparse import parse_qsl

else:
    from urllib.parse import unquote, parse_qsl


def make_callable_from_sync(func):
    """
    Decorator, which when placed before inlineCallbacks allows the function to be
    called from a synchronous environment with a reactor running in a different thread.
    The result returns synchronously.
    """
    def wrapped_func(*args, **kwargs):
        return threads.blockingCallFromThread(reactor, func, *args, **kwargs)
    return wrapped_func

def get_app_dict(app_list):
    """
    Create app dict from list of apps
    """
    return {app.app_name: app.display_app_name for app in app_list}

def invalid_apps(total_app_list, selected_app_list):
    """
    tests if any apps in an app list
    are invalid based on the viewable apps using
    the permissions of the authtoken from the supplied request

    :param selected_app_list: The app list being tested
    :param total_app_list: The list of all valid apps
    :return invalid_apps: The list of invalid apps
    """

    app_name_dict = get_app_dict(total_app_list)
    invalid_app_list = [app for app in selected_app_list if app not in app_name_dict]
    return invalid_app_list

def validate_write_request(request, total_app_list):
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
    invalid_app_list = invalid_apps(total_app_list, jsonified_app_list)

    if invalid_app_list:
        raise Errors.SpacebridgeRestError('Error: Could not find app(s)={}'.format(invalid_app_list), 400)

    return app_list
