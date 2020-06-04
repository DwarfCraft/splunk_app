"""
(C) 2019 Splunk Inc. All rights reserved.

Module to process App List Requests
"""
import json
from spacebridgeapp.util import constants
from spacebridgeapp.logging import setup_logging
from twisted.internet import defer
from twisted.web import http
from spacebridgeapp.data.app_list_data import App, DashboardAppList
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.util.app_info import fetch_display_app_name
from spacebridgeapp.util.constants import USER_META_COLLECTION_NAME, DASHBOARD_APP_LIST, KEY, APP_NAMES, USER_KEY


LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_app_list_request_processor.log",
                       "app_list_request_processor")


@defer.inlineCallbacks
def process_dashboard_app_list_set_request(request_context,
                                           client_single_request,
                                           single_server_response,
                                           async_client_factory):
    """
    This method will process a DashboardAppListSetRequest.  Given a list of appNames from the client the
    dashboard_app_list object under the user_meta collection in KVStore will be updated with these values after
    validating the app names.

    :param request_context:
    :param client_single_request:
    :param single_server_response:
    :param async_client_factory:
    :return:
    """
    # validate request params
    app_names = client_single_request.dashboardAppListSetRequest.appNames

    # async clients
    async_splunk_client = async_client_factory.splunk_client()
    async_kvstore_client = async_client_factory.kvstore_client()

    # Validation only required if app_names are specified
    if app_names:
        # fetch master app name list used to validate
        all_app_names = yield fetch_app_names(request_context=request_context, async_splunk_client=async_splunk_client)
        all_app_name_list = [app.app_name for app in all_app_names]

        # validate all app names
        for app_name in app_names:
            if app_name not in all_app_name_list:
                raise SpacebridgeApiRequestError("The appName={} is invalid.  Unable to set appName list."
                                                 .format(app_name))

    # Store names in kvstore
    dashboard_app_list = yield set_dashboard_app_list(request_context=request_context,
                                                      app_names=app_names,
                                                      async_kvstore_client=async_kvstore_client,
                                                      async_splunk_client=async_splunk_client)

    # populate app list response
    single_server_response.dashboardAppListSetResponse.SetInParent()

    defer.returnValue(dashboard_app_list)


@defer.inlineCallbacks
def fetch_dashboard_app_list(request_context,
                             async_kvstore_client=None,
                             async_splunk_client=None):
    """
    Helper to fetch dashboard_app_list from user_meta
    :param request_context:
    :param async_kvstore_client:
    :return:
    """
    if async_kvstore_client and async_splunk_client:
        response = yield async_kvstore_client.async_kvstore_get_request(collection=USER_META_COLLECTION_NAME,
                                                                        auth_header=request_context.auth_header,
                                                                        owner=request_context.current_user,
                                                                        key_id=DASHBOARD_APP_LIST)
        if response.code == http.OK:
            response_json = yield response.json()
            if response_json:
                app_names = json.loads(response_json[APP_NAMES])

                # make sure apps are not disabled/invisible (fetch app names filters these out)
                valid_app_names = yield fetch_app_names(request_context=request_context, async_splunk_client=async_splunk_client)
                valid_app_names = [app.app_name for app in valid_app_names]

                defer.returnValue([app for app in app_names if app in valid_app_names])

        elif response.code != http.NOT_FOUND:
            error = yield response.text()
            error_message = "Unable to find dashboard_app_list in user_meta collection. status_code={}, error={}"\
                .format(response.code, error)
            raise SpacebridgeApiRequestError(error_message)

    # Return None no data if meta isn't available
    defer.returnValue(None)


@defer.inlineCallbacks
def set_dashboard_app_list(request_context, app_names=None, async_kvstore_client=None, async_splunk_client=None):
    """
    Helper to set dashboard_app_list object in user_meta
    :param request_context:
    :param app_names:
    :param async_kvstore_client:
    :return:
    """
    # Get dashboard_meta collection if key exists
    existing_app_names = yield fetch_dashboard_app_list(request_context=request_context,
                                                        async_kvstore_client=async_kvstore_client,
                                                        async_splunk_client=async_splunk_client)

    # We strictly overwrite on set
    dashboard_app_list = DashboardAppList(app_names=app_names)
    # We need to modify the object before we dump it to write to kvstore, but we don't want
    # what is returned to be modified
    # We need to write the json dumped version of the app names to kvstore
    kvstore_data = {
        KEY: DASHBOARD_APP_LIST,
        USER_KEY: dashboard_app_list._user,
        APP_NAMES: json.dumps(list(dashboard_app_list.app_names)),
    }

    # if key doesn't exist we create new key, otherwise update existing one
    if existing_app_names is None:
        # Create new dashboard_meta collection
        response = yield async_kvstore_client.async_kvstore_post_request(
            collection=USER_META_COLLECTION_NAME,
            data=json.dumps(kvstore_data),
            owner=request_context.current_user,
            auth_header=request_context.system_auth_header)
    else:
        # Update existing collection
        response = yield async_kvstore_client.async_kvstore_post_request(
            collection=USER_META_COLLECTION_NAME,
            data=json.dumps(kvstore_data),
            key_id=DASHBOARD_APP_LIST,  # To update a collection we need to specify the key
            owner=request_context.current_user,
            auth_header=request_context.system_auth_header)

    # Report any errors
    if response.code not in [http.OK, http.CREATED]:
        error = yield response.text()
        error_message = "Failed Dashboard App List Set Request. status_code={}, error={}".format(response.code, error)
        raise SpacebridgeApiRequestError(error_message)

    LOGGER.info("Successful Dashboard App List Set Request")
    defer.returnValue(dashboard_app_list)


@defer.inlineCallbacks
def process_dashboard_app_list_get_request(request_context,
                                           client_single_request,
                                           single_server_response,
                                           async_client_factory):
    """
    This method will process a DashboardAppListGetRequest.  This will return the list of app_names found under the
    dashboard_app_list key in the user_meta KVStore collection.

    :param request_context:
    :param client_single_request:
    :param single_server_response:
    :param async_client_factory:
    :return:
    """
    # async clients
    async_kvstore_client = async_client_factory.kvstore_client()
    async_splunk_client = async_client_factory.splunk_client()

    # Get dashboard_meta collection if key exists
    app_names = yield fetch_dashboard_app_list_with_default(request_context=request_context,
                                                            async_kvstore_client=async_kvstore_client,
                                                            async_splunk_client=async_splunk_client)

    # populate app list response
    single_server_response.dashboardAppListGetResponse.appNames.extend(app_names)

    defer.returnValue(app_names)


@defer.inlineCallbacks
def fetch_dashboard_app_list_with_default(request_context,
                                          default_app_names=None,
                                          async_kvstore_client=None,
                                          async_splunk_client=None):
    """
    Wrapper around fetch_dashboard_app_list method to return a default value of []
    in case dashboard_app_list not specified

    :param request_context:
    :param default_app_names:
    :param async_kvstore_client:
    :param async_splunk_client:
    :return:
    """

    if default_app_names is None:
        default_app_names = []

    # Get dashboard_meta collection if key exists
    app_names = yield fetch_dashboard_app_list(request_context=request_context,
                                               async_kvstore_client=async_kvstore_client,
                                               async_splunk_client=async_splunk_client)

    # if no app_names are specified the default should be all apps (no filter)
    # Distinguishing an empty list from None is important here as
    # an empty list is a valid stored state in kvstore, while None indicates
    # that there we were unable to fetch the data from kvstore.
    # The empty list allows us to filter by all apps implicitly
    defer.returnValue(app_names if app_names is not None else default_app_names)


@defer.inlineCallbacks
def process_app_list_request(request_context,
                             client_single_request,
                             single_server_response,
                             async_client_factory):
    """
    This method will create an async http request to splunk api and returns a list of app names and their corresponding
    display app names in a single_server_response object

    :param request_context:
    :param client_single_request: incoming request
    :param single_server_response: outgoing response
    :param async_client_factory: async client used to make https request
    :return:
    """

    # async clients
    async_splunk_client = async_client_factory.splunk_client()

    # fetch app lists
    app_list = yield fetch_app_names(request_context=request_context, async_splunk_client=async_splunk_client)

    app_protos = [app.to_protobuf() for app in app_list]

    # populate app list response
    single_server_response.appListResponse.apps.extend(app_protos)

    LOGGER.debug("Finished populating response for app list request")


@defer.inlineCallbacks
def fetch_app_names(request_context,
                    async_splunk_client=None):
    """
    Method makes async http call to get app list and returns the app names and display app names

    :param request_context:
    :param async_splunk_client:
    :return:
    """

    params = {'output_mode': 'json',
              'search': '(visible = true AND disabled = false)',
              'count': 0}

    response = yield async_splunk_client.async_get_app_list_request(auth_header=request_context.auth_header,
                                                                    params=params)

    if response.code != http.OK:
        response_text = yield response.text()
        raise SpacebridgeApiRequestError("Failed fetch_app_names response.code={}, response.text={}"
                                         .format(response.code, response_text))

    response_text = yield response.text()
    # convert to json object
    response_json = yield response.json()
    entry_json_list = response_json.get('entry', [])
    LOGGER.debug('fetch_app_names response={}, code={}'
                 .format([app.get('name') for app in entry_json_list], response.code))
    app_list = []

    for entry_json in entry_json_list:
        app_name = entry_json.get('name')

        # Populate display_app_name
        display_app_name = ""
        if async_splunk_client is not None:
            display_app_name = yield fetch_display_app_name(request_context=request_context,
                                                            app_name=app_name,
                                                            async_splunk_client=async_splunk_client)
            app = App(app_name=app_name, display_app_name=display_app_name)
            app_list.append(app)

    defer.returnValue(app_list)
