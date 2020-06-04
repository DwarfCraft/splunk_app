"""
(C) 2019 Splunk Inc. All rights reserved.

Module to process Subscription requests
"""
from functools import partial
from uuid import uuid4
from twisted.internet import defer
from twisted.web import http

from spacebridgeapp.data.visualization_type import VisualizationType
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError, OperationHaltedError
from spacebridgeapp.request.dashboard_request_processor import get_search_job_content
from spacebridgeapp.subscriptions.subscription_helpers import generate_search_hash, refresh_to_seconds
from spacebridgeapp.subscriptions.subscription_map_requests import construct_cluster_map_post_search, \
    validate_choropleth_map_params, construct_choropleth_map_post_search
from spacebridgeapp.subscriptions.subscription_requests import validate_dashboard_search
from spacebridgeapp.subscriptions.subscription_search_requests import create_job_from_search
from spacebridgeapp.util import constants

from spacebridgeapp.util.time_utils import get_expiration_timestamp_str, get_current_timestamp_str
from spacebridgeapp.search.input_token_support import set_default_token_values
from spacebridgeapp.data.subscription_data import Subscription, SubscriptionSearch, SubscriptionCredential, \
    SearchUpdate
from spacebridgeapp.data.dashboard_data import DashboardVisualizationId, Search
from spacebridgeapp.data.search_type import SearchType
from spacebridgeapp.subscriptions.udf_subscriptions import create_search_from_datasource
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, SEARCHES_COLLECTION_NAME, \
    SUBSCRIPTIONS_COLLECTION_NAME, CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_REQUEST, \
    CLIENT_SUBSCRIBE_DASHBOARD_INPUT_SEARCH_REQUEST, CLIENT_SUBSCRIBE_SAVED_SEARCH_REQUEST, \
    CLIENT_SUBSCRIBE_UDF_DATASOURCE, NOBODY, CLIENT_SUBSCRIBE_DRONE_MODE_TV, \
    SUBSCRIPTION_CREDENTIALS_COLLECTION_NAME, CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_CLUSTER_MAP, \
    CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_CHOROPLETH_MAP, SEARCH_UPDATES_COLLECTION_NAME, JWT_TOKEN_TYPE, \
    SPLUNK_SESSION_TOKEN_TYPE, CLIENT_SUBSCRIBE_DRONE_MODE_IPAD
from spacebridgeapp.request.request_processor import get_splunk_cookie, JWTAuthHeader
from spacebridgeapp.request.drone_mode_request_processor import process_subscribe_drone_mode_tv, \
    process_subscribe_drone_mode_ipad
from spacebridgeapp.logging import setup_logging

from spacebridgeapp.dashboard.dashboard_helpers import parse_dashboard_id, get_dashboard_input_tokens

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_subscription_request_processor.log",
                       "subscription_request_processor")


@defer.inlineCallbacks
def _spawn_search_job(request_context, async_splunk_client, subscription_search, input_tokens, sid):
    owner, app_name, dashboard_name = parse_dashboard_id(subscription_search.dashboard_id)
    sid = yield create_job_from_search(request_context.auth_header, subscription_search, app_name,
                                       request_context.current_user, input_tokens, async_splunk_client, sid)

    LOGGER.info("Created search job sid={}".format(sid))
    defer.returnValue(sid)


@defer.inlineCallbacks
def process_subscribe_request(request_context,
                              client_subscription_message=None,
                              server_subscription_response=None,
                              async_client_factory=None):
    """
    Process Different Subscribe Requests
    :param request_context:
    :param client_subscription_message:
    :param server_subscription_response:
    :param async_client_factory:
    :return:
    """

    if client_subscription_message.clientSubscribeRequest.HasField(CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_REQUEST):
        LOGGER.info("type=CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_REQUEST")
        yield process_subscribe_dashboard_visualization_request(
            request_context,
            client_subscription_message,
            server_subscription_response,
            async_client_factory)

    elif client_subscription_message.clientSubscribeRequest.HasField(CLIENT_SUBSCRIBE_SAVED_SEARCH_REQUEST):
        LOGGER.info("type=CLIENT_SUBSCRIBE_SAVED_SEARCH_REQUEST")
        yield process_subscribe_saved_search_request(
            request_context,
            client_subscription_message,
            server_subscription_response,
            async_client_factory)

    elif client_subscription_message.clientSubscribeRequest.HasField(CLIENT_SUBSCRIBE_DASHBOARD_INPUT_SEARCH_REQUEST):
        LOGGER.info("type=CLIENT_SUBSCRIBE_DASHBOARD_INPUT_SEARCH_REQUEST")
        yield process_subscribe_dashboard_input_search_request(
            request_context,
            client_subscription_message,
            server_subscription_response,
            async_client_factory)

    elif client_subscription_message.clientSubscribeRequest.HasField(CLIENT_SUBSCRIBE_UDF_DATASOURCE):
        LOGGER.info("type=CLIENT_SUBSCRIBE_UDF_DATASOURCE")
        yield process_subscribe_udf_datasource(
            request_context,
            client_subscription_message,
            server_subscription_response,
            async_client_factory)

    elif client_subscription_message.clientSubscribeRequest.HasField(CLIENT_SUBSCRIBE_DRONE_MODE_TV):
        LOGGER.info("type=CLIENT_SUBSCRIBE_DRONE_MODE_TV")
        yield process_subscribe_drone_mode_tv(
            request_context,
            client_subscription_message,
            server_subscription_response,
            async_client_factory)

    elif client_subscription_message.clientSubscribeRequest.HasField(CLIENT_SUBSCRIBE_DRONE_MODE_IPAD):
        LOGGER.info("type=CLIENT_SUBSCRIBE_DRONE_MODE_IPAD")
        yield process_subscribe_drone_mode_ipad(
            request_context,
            client_subscription_message,
            server_subscription_response,
            async_client_factory)


@defer.inlineCallbacks
def process_subscribe_update_request(request_context,
                                     client_subscription_message=None,
                                     server_subscription_response=None,
                                     async_kvstore_client=None):
    client_subscription_update = client_subscription_message.clientSubscriptionUpdate
    server_subscription_response.serverSubscribeResponse.SetInParent()

    if client_subscription_update.HasField(CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_CLUSTER_MAP):
        LOGGER.info("type=CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_CLUSTER_MAP")
        yield process_dashboard_visualization_map_update(
            request_context=request_context,
            construct_post_search_string=construct_cluster_map_post_search,
            dashboard_visualization_map=client_subscription_update.dashboardVisualizationClusterMap,
            client_subscription_message=client_subscription_message,
            server_subscription_response=server_subscription_response,
            async_kvstore_client=async_kvstore_client)

    elif client_subscription_update.HasField(CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_CHOROPLETH_MAP):
        LOGGER.info("type=CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_CHOROPLETH_MAP")
        yield process_dashboard_visualization_map_update(
            request_context=request_context,
            validate_map_update=validate_choropleth_map_params,
            construct_post_search_string=construct_choropleth_map_post_search,
            dashboard_visualization_map=client_subscription_update.dashboardVisualizationChoroplethMap,
            client_subscription_message=client_subscription_message,
            server_subscription_response=server_subscription_response,
            async_kvstore_client=async_kvstore_client)


@defer.inlineCallbacks
def process_dashboard_visualization_map_update(request_context,
                                               validate_map_update=None,
                                               construct_post_search_string=None,
                                               dashboard_visualization_map=None,
                                               client_subscription_message=None,
                                               server_subscription_response=None,
                                               async_kvstore_client=None):
    # Retrieve Params
    client_subscription_update = client_subscription_message.clientSubscriptionUpdate
    subscription_id = client_subscription_update.subscriptionId

    # Validate subscription_id
    LOGGER.debug('Start process_subscription_update subscription_id=%s', subscription_id)

    # See if subscription_id exists in KVStore
    get_response = yield async_kvstore_client.async_kvstore_get_request(
        collection=SUBSCRIPTIONS_COLLECTION_NAME,
        key_id=subscription_id,
        owner=NOBODY,
        auth_header=request_context.auth_header)

    if get_response.code != http.OK:
        error = yield get_response.text()
        error_message = "Update failed. Subscription ID Not Found! status_code={}, error={},subscription_id={}" \
            .format(get_response.code, error, subscription_id)
        raise SpacebridgeApiRequestError(error_message, status_code=get_response.code)

    yield process_post_search(request_context=request_context,
                              validate_map_update=validate_map_update,
                              construct_post_search_string=construct_post_search_string,
                              dashboard_visualization_map=dashboard_visualization_map,
                              subscription_id=subscription_id,
                              server_subscription_response=server_subscription_response,
                              async_kvstore_client=async_kvstore_client)


@defer.inlineCallbacks
def process_post_search(request_context,
                        validate_map_update=None,
                        construct_post_search_string=None,
                        dashboard_visualization_map=None,
                        subscription_id=None,
                        server_subscription_response=None,
                        async_kvstore_client=None):

    if validate_map_update:
        validate_error_list = validate_map_update(dashboard_visualization_map)

        if validate_error_list:
            error_message = ','.join(validate_error_list)
            raise SpacebridgeApiRequestError(error_message, status_code=http.BAD_REQUEST)

    post_search = construct_post_search_string(dashboard_visualization_map)
    subscription_update = SearchUpdate(post_search=post_search, key=subscription_id)

    yield process_subscription_post_search(request_context,
                                           subscription_update,
                                           server_subscription_response,
                                           async_kvstore_client)


@defer.inlineCallbacks
def process_subscribe_dashboard_input_search_request(request_context,
                                                     client_subscription_message=None,
                                                     server_subscription_response=None,
                                                     async_client_factory=None):
    """
    Process Subscribe Dashbaord Input Search Requests from Clients,
    will return subscription_id in successful subscription
    :param request_context:
    :param client_subscription_message:
    :param server_subscription_response:
    :param async_client_factory:
    :return:
    """
    # async clients
    async_splunk_client = async_client_factory.splunk_client()
    async_kvstore_client = async_client_factory.kvstore_client()

    # retrieve request params
    ttl_seconds = client_subscription_message.clientSubscribeRequest.ttlSeconds
    dashboard_input_search_subscribe = client_subscription_message.clientSubscribeRequest.dashboardInputSearchSubscribe
    dashboard_id = dashboard_input_search_subscribe.dashboardId
    query_id = dashboard_input_search_subscribe.queryId
    input_tokens = dict(dashboard_input_search_subscribe.inputTokens)

    # validate input search
    dashboard_description = yield validate_dashboard_search(request_context=request_context,
                                                            dashboard_id=dashboard_id,
                                                            type_id=query_id,
                                                            search_type=SearchType.INPUT,
                                                            input_tokens=input_tokens,
                                                            async_kvstore_client=async_kvstore_client,
                                                            async_splunk_client=async_splunk_client)

    dashboard_defn = dashboard_description.definition

    default_input_tokens = get_dashboard_input_tokens(dashboard_defn)

    # Pull out validated input_token
    user_roles = yield fetch_user_roles(request_context.auth_header, async_splunk_client)
    input_token = dashboard_description.get_input_token_by_query_id(query_id)
    search_defn = input_token.input_type.dynamic_options.search
    search_key = generate_search_hash(dashboard_id, query_id, input_tokens, user_roles,
                                      refresh_interval=None)

    spawn_search_job = partial(_spawn_search_job, request_context, async_splunk_client)

    yield lazy_load_subscription_search(request_context=request_context,
                                        dashboard_id=dashboard_id,
                                        search_type_id=query_id,
                                        search_type=SearchType.INPUT.value,
                                        search_defn=search_defn,
                                        search_key=search_key,
                                        input_tokens=input_tokens,
                                        dashboard_defn=dashboard_defn,
                                        async_kvstore_client=async_kvstore_client,
                                        async_splunk_client=async_splunk_client,
                                        user_roles=user_roles,
                                        spawn_search_job=spawn_search_job,
                                        shard_id=request_context.shard_id,
                                        default_input_tokens=default_input_tokens)

    # Create Subscription
    subscription_id = yield create_subscription(request_context=request_context,
                                                search_key=search_key,
                                                ttl_seconds=ttl_seconds,
                                                shard_id=request_context.shard_id,
                                                async_splunk_client=async_splunk_client,
                                                async_kvstore_client=async_kvstore_client,
                                                visualization_id=dashboard_id)

    # Set ServerSubscribeResponse with created subscription key
    server_subscription_response.subscriptionId = subscription_id
    # TODO: Return fields about the search back to the user
    server_subscription_response.serverSubscribeResponse.SetInParent()


@defer.inlineCallbacks
def process_subscribe_saved_search_request(request_context,
                                           client_subscription_message=None,
                                           server_subscription_response=None,
                                           async_client_factory=None):
    """
    Process saved search subscribe requests from clients, will return subscription_id in successful subscription
    :param request_context:
    :param client_subscription_message:
    :param server_subscription_response:
    :param async_client_factory:
    :return:
    """

    # async clients
    async_splunk_client = async_client_factory.splunk_client()
    async_kvstore_client = async_client_factory.kvstore_client()

    # retrieve request params
    ttl_seconds = client_subscription_message.clientSubscribeRequest.ttlSeconds
    saved_search_subscribe = client_subscription_message.clientSubscribeRequest.clientSavedSearchSubscribe
    saved_search_id = saved_search_subscribe.savedSearchId
    input_tokens = dict(saved_search_subscribe.inputTokens)
    search = Search(ref=saved_search_id)

    user_roles = yield fetch_user_roles(request_context.auth_header, async_splunk_client)
    search_key = generate_search_hash(saved_search_id, input_tokens, user_roles,
                                      refresh_interval=None,
                                      dashboard_id=request_context.shard_id)

    spawn_search_job = partial(_spawn_search_job, request_context, async_splunk_client)

    yield lazy_load_subscription_search(request_context=request_context,
                                        search_type_id=saved_search_id,
                                        search_type=SearchType.SAVED_SEARCH.value,
                                        search_defn=search,
                                        search_key=search_key,
                                        input_tokens=input_tokens,
                                        async_kvstore_client=async_kvstore_client,
                                        async_splunk_client=async_splunk_client,
                                        user_roles=user_roles,
                                        spawn_search_job=spawn_search_job,
                                        shard_id=request_context.shard_id)

    # Create Subscription
    subscription_id = yield create_subscription(request_context=request_context,
                                                search_key=search_key,
                                                ttl_seconds=ttl_seconds,
                                                shard_id=request_context.shard_id,
                                                async_splunk_client=async_splunk_client,
                                                async_kvstore_client=async_kvstore_client,
                                                visualization_id=search_key)

    # Set ServerSubscribeResponse with created subscription key
    server_subscription_response.subscriptionId = subscription_id
    # TODO: Return fields about the search back to the user
    server_subscription_response.serverSubscribeResponse.SetInParent()


@defer.inlineCallbacks
def process_subscribe_udf_datasource(request_context, client_subscription_message, server_subscription_response,
                                     async_client_factory):
    """
    Takes a requestof type clientSubscribeRequest.udfDataSourceSubscribe. Validates that the provided dashboard
    actually has the requested data source. If it does, we create a pubsub entry in KV store and send back
    the subscription id as we do with all pubsub requests
    :param request_context:
    :param client_subscription_message: UdfDataSourceSubscribe
    :param server_subscription_response: ServerSubscriptionResponse
    :param async_client_factory:
    :return: None, mutates the server subscription response input object.
    """
    # async clients
    async_splunk_client = async_client_factory.splunk_client()
    async_kvstore_client = async_client_factory.kvstore_client()

    ttl_seconds = client_subscription_message.clientSubscribeRequest.ttlSeconds
    udf_ds_subscribe = client_subscription_message.clientSubscribeRequest.udfDataSourceSubscribe
    dashboard_id = udf_ds_subscribe.dashboardId
    datasource_id = udf_ds_subscribe.dataSourceId
    input_tokens = dict(udf_ds_subscribe.inputTokens)

    dashboard_description = yield validate_dashboard_search(request_context=request_context,
                                                            dashboard_id=dashboard_id,
                                                            search_type=SearchType.DATA_SOURCE,
                                                            type_id=datasource_id,
                                                            input_tokens=input_tokens,
                                                            async_kvstore_client=async_kvstore_client,
                                                            async_splunk_client=async_splunk_client)

    datasources = [d for d in dashboard_description.definition.udf_data_sources if d.name == datasource_id]
    # The validate dashboard search call above verifies that exactly one data source matches the given id, so we can
    # safely take the first element
    search_defn = create_search_from_datasource(datasources[0])
    user_roles = yield fetch_user_roles(request_context.auth_header, async_splunk_client)
    search_key = generate_search_hash(dashboard_id, datasource_id, input_tokens, user_roles,
                                      refresh_interval=refresh_to_seconds(search_defn.refresh))

    spawn_search_job = partial(_spawn_search_job, request_context, async_splunk_client)

    dashboard_defn = dashboard_description.definition

    yield lazy_load_subscription_search(request_context=request_context,
                                        dashboard_id=dashboard_id,
                                        search_type_id=datasource_id,
                                        search_type=SearchType.VISUALIZATION.value,
                                        search_defn=search_defn,
                                        search_key=search_key,
                                        input_tokens=input_tokens,
                                        dashboard_defn=dashboard_defn,
                                        async_kvstore_client=async_kvstore_client,
                                        async_splunk_client=async_splunk_client,
                                        user_roles=user_roles,
                                        spawn_search_job=spawn_search_job,
                                        shard_id=request_context.shard_id)

    # Create Subscription
    # TODO: no visualization_id here, and param is required in function
    subscription_id = yield create_subscription(request_context=request_context,
                                                search_key=search_key,
                                                ttl_seconds=ttl_seconds,
                                                shard_id=request_context.shard_id,
                                                async_splunk_client=async_splunk_client,
                                                async_kvstore_client=async_kvstore_client,
                                                visualization_id=datasource_id)

    # Set ServerSubscribeResponse with created subscription key
    server_subscription_response.subscriptionId = subscription_id
    # TODO: Return fields about the search back to the user
    server_subscription_response.serverSubscribeResponse.SetInParent()


@defer.inlineCallbacks
def process_subscribe_dashboard_visualization_request(request_context,
                                                      client_subscription_message,
                                                      server_subscription_response,
                                                      async_client_factory):
    """
    Process Subscribe Dashboard Visualization Requests from Clients,
    will return subscription_id in successful subscription
    :param request_context:
    :param client_subscription_message:
    :param server_subscription_response:
    :param async_client_factory:
    :return:
    """
    LOGGER.debug("process_subscribe_dashboard_visualization_request start")
    # async clients
    async_splunk_client = async_client_factory.splunk_client()
    async_kvstore_client = async_client_factory.kvstore_client()

    # retrieve request params
    ttl_seconds = client_subscription_message.clientSubscribeRequest.ttlSeconds
    dashboard_visualization_subscribe = client_subscription_message.clientSubscribeRequest.dashboardVisualizationSubscribe
    dashboard_visualization_id = DashboardVisualizationId()
    dashboard_visualization_id.from_protobuf(dashboard_visualization_subscribe.dashboardVisualizationId)
    dashboard_id = dashboard_visualization_id.dashboard_id
    visualization_id = dashboard_visualization_id.visualization_id
    input_tokens = dict(dashboard_visualization_subscribe.inputTokens)

    # Validate dashboard_id, visualization_id excepts if fail, return dashboard_description if ok
    dashboard_description = yield validate_dashboard_search(request_context=request_context,
                                                            dashboard_id=dashboard_id,
                                                            type_id=visualization_id,
                                                            input_tokens=input_tokens,
                                                            async_kvstore_client=async_kvstore_client,
                                                            async_splunk_client=async_splunk_client)

    dashboard_defn = dashboard_description.definition

    default_input_tokens = get_dashboard_input_tokens(dashboard_defn)

    visualization = dashboard_description.get_visualization(visualization_id)
    visualization_type = visualization.visualization_type

    user_roles = yield fetch_user_roles(request_context.auth_header, async_splunk_client)

    search_id = visualization.search.id

    if not search_id:
        search_id = visualization_id

    search_key = generate_search_hash(dashboard_id, search_id, input_tokens, user_roles,
                                      refresh_interval=refresh_to_seconds(visualization.search.refresh))

    spawn_search_job = partial(_spawn_search_job, request_context, async_splunk_client)

    yield lazy_load_subscription_search(request_context=request_context,
                                        dashboard_id=dashboard_id,
                                        search_type_id=visualization_id,
                                        search_type=SearchType.VISUALIZATION.value,
                                        search_defn=visualization.search,
                                        search_key=search_key,
                                        input_tokens=input_tokens,
                                        dashboard_defn=dashboard_defn,
                                        async_kvstore_client=async_kvstore_client,
                                        async_splunk_client=async_splunk_client,
                                        user_roles=user_roles,
                                        spawn_search_job=spawn_search_job,
                                        shard_id=request_context.shard_id,
                                        default_input_tokens=default_input_tokens,
                                        visualization_type=visualization_type
                                        )

    subscription_id = yield create_subscription(request_context=request_context,
                                                ttl_seconds=ttl_seconds,
                                                search_key=search_key,
                                                shard_id=request_context.shard_id,
                                                async_splunk_client=async_splunk_client,
                                                async_kvstore_client=async_kvstore_client,
                                                visualization_id=visualization_id)

    # Set ServerSubscribeResponse with created subscription key
    server_subscription_response.subscriptionId = subscription_id
    # TODO: Return fields about the search back to the user
    server_subscription_response.serverSubscribeResponse.SetInParent()

    if dashboard_visualization_subscribe.HasField(CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_CLUSTER_MAP):
        yield process_post_search(request_context=request_context,
                                  construct_post_search_string=construct_cluster_map_post_search,
                                  dashboard_visualization_map=dashboard_visualization_subscribe.dashboardVisualizationClusterMap,
                                  subscription_id=subscription_id,
                                  server_subscription_response=server_subscription_response,
                                  async_kvstore_client=async_kvstore_client)

    elif dashboard_visualization_subscribe.HasField(CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_CHOROPLETH_MAP):
        yield process_post_search(request_context=request_context,
                                  validate_map_update=validate_choropleth_map_params,
                                  construct_post_search_string=construct_choropleth_map_post_search,
                                  dashboard_visualization_map=dashboard_visualization_subscribe.dashboardVisualizationChoroplethMap,
                                  subscription_id=subscription_id,
                                  server_subscription_response=server_subscription_response,
                                  async_kvstore_client=async_kvstore_client)


@defer.inlineCallbacks
def lazy_load_subscription_search(request_context, input_tokens, search_key,
                                  search_type, search_type_id, search_defn, async_kvstore_client, async_splunk_client,
                                  user_roles, shard_id, spawn_search_job,
                                  dashboard_defn=None, dashboard_id=None, default_input_tokens=None, visualization_type=None):
    """

    :param request_context:
    :param input_tokens:
    :param search_key:
    :param search_type:
    :param search_type_id:
    :param search_defn:
    :param async_kvstore_client:
    :param async_splunk_client:
    :param user_roles:
    :param shard_id:
    :param spawn_search_job:
    :param dashboard_defn:
    :param dashboard_id:
    :param default_input_tokens:
    :return:
    """

    if default_input_tokens is None:
        default_input_tokens = {}

    if type != SearchType.SAVED_SEARCH:
        # Set Default input_token values
        set_default_token_values(input_tokens, default_input_tokens)

    parent_id = None
    search_query = search_defn.query

    sid = None
    if search_defn.base:
        parent_search_defn = dashboard_defn.find_base_search(search_defn.base)

        parent_search_key = generate_search_hash(dashboard_id, parent_search_defn.id, input_tokens,
                                                 user_roles,
                                                 refresh_interval=refresh_to_seconds(parent_search_defn.refresh))

        LOGGER.debug("Base search exists, base=%s", parent_search_defn)

        parent = yield lazy_load_subscription_search(request_context=request_context,
                                                     input_tokens=input_tokens,
                                                     search_key=parent_search_key,
                                                     search_type=SearchType.ROOT.value,
                                                     search_type_id=parent_search_key,
                                                     search_defn=parent_search_defn,
                                                     async_kvstore_client=async_kvstore_client,
                                                     async_splunk_client=async_splunk_client,
                                                     user_roles=user_roles,
                                                     shard_id=request_context.shard_id,
                                                     spawn_search_job=spawn_search_job,
                                                     dashboard_defn=parent_search_defn,
                                                     dashboard_id=dashboard_id,
                                                     default_input_tokens=default_input_tokens,
                                                     visualization_type=visualization_type)
        sid = parent.sid
        parent_id = parent.key()

    # i.e. no parent search
    if not sid:
        sid = search_key

    subscription_search = build_subscription_search(request_context, dashboard_id, search_defn, search_query,
                                                    input_tokens, parent_id, search_key, search_type,
                                                    search_type_id, shard_id, sid,
                                                    visualization_type=visualization_type)
    params = {}
    if visualization_type is not None and VisualizationType(visualization_type) == VisualizationType.DASHBOARD_VISUALIZATION_EVENT:
        params[constants.COUNT] = '200'

    job_status = yield get_search_job_content(request_context.auth_header, subscription_search.owner,
                                              SPACEBRIDGE_APP_NAME, subscription_search.sid, async_splunk_client, params=params)
    if not job_status:
        LOGGER.debug("Start search job, sid=%s", sid)
        yield spawn_search_job(subscription_search, input_tokens, sid)

    http_result = yield create_search(request_context,
                                      subscription_search,
                                      async_kvstore_client)

    if http_result not in [http.CREATED, http.CONFLICT]:
        raise SpacebridgeApiRequestError(message='Failed to create subscription search', status_code=http_result)

    defer.returnValue(subscription_search)


@defer.inlineCallbacks
def fetch_user_roles(auth_header, async_splunk_client):
    """
    Fetch the roles for an input auth token. For example, roles could be
    admin, power user, etc...
    """
    resp = yield async_splunk_client.async_get_current_context(auth_header)
    if resp.code == http.OK:
        user_context = yield resp.json()
        defer.returnValue(user_context["entry"][0]["content"]["roles"])

    defer.returnValue([])


def build_subscription_search(request_context,
                              dashboard_id,
                              search_defn,
                              search_query,
                              input_tokens,
                              parent_id,
                              search_key,
                              search_type,
                              search_type_id,
                              shard_id,
                              sid,
                              visualization_type=None):
    try:
        # Dashboard Definition refresh will override and refresh_interval
        refresh_interval_seconds = refresh_to_seconds(search_defn.refresh)

        # extract username and password
        query = search_query
        earliest_time = search_defn.earliest
        latest_time = search_defn.latest
        sample_ratio = search_defn.sample_ratio
        ref = search_defn.ref
        base = search_defn.base

        next_update_time = get_expiration_timestamp_str(ttl_seconds=refresh_interval_seconds)
        last_update_time = get_current_timestamp_str()
        # Create Search object
        subscription_search = SubscriptionSearch(_key=search_key,
                                                 dashboard_id=dashboard_id,
                                                 search_type_id=search_type_id,
                                                 search_type=search_type,
                                                 owner=request_context.current_user,
                                                 ref=ref,
                                                 base=base,
                                                 sid=sid,
                                                 query=query,
                                                 parent_search_key=parent_id,
                                                 earliest_time=earliest_time,
                                                 latest_time=latest_time,
                                                 sample_ratio=sample_ratio,
                                                 refresh_interval_seconds=refresh_interval_seconds,
                                                 next_update_time=next_update_time,
                                                 last_update_time=last_update_time,
                                                 input_tokens=input_tokens,
                                                 shard_id=shard_id,
                                                 visualization_type=visualization_type)
    except Exception as e:
        LOGGER.exception("Failed to build subscription_search")
        raise e

    return subscription_search


@defer.inlineCallbacks
def create_search(request_context,
                  subscription_search,
                  async_kvstore_client):
    """
    Create a subscription search object in kvstore collection [searches]
    :param request_context:
    :param subscription_search:
    :param async_kvstore_client:
    :return:
    """

    http_result = yield save_search(request_context=request_context,
                                    subscription_search=subscription_search,
                                    async_kvstore_client=async_kvstore_client)

    defer.returnValue(http_result)


@defer.inlineCallbacks
def save_search(request_context,
                subscription_search=None,
                async_kvstore_client=None):
    """
    Method to save_search to kvstore, updates if search_key is passed in
    :param request_context:
    :param subscription_search:
    :param async_kvstore_client:
    :return:
    """

    # create search and return _key
    response = yield async_kvstore_client.async_kvstore_post_request(
        collection=SEARCHES_COLLECTION_NAME,
        data=subscription_search.to_json(),
        auth_header=request_context.auth_header)

    if response.code == http.OK or response.code == http.CREATED:
        LOGGER.debug("Subscription Search Created. search_key=%s", subscription_search.key())
        defer.returnValue(http.CREATED)

    # This is the case when user tries to save a subscription_search but a search with the same _key exists
    if response.code == http.CONFLICT:
        LOGGER.debug("Subscription Search was already Created. search_key=%s", subscription_search.key())
        defer.returnValue(http.CONFLICT)

    # Return Error in the case where response isn't successful
    error = yield response.text()
    error_message = "Failed to create Subscription Search. status_code={}, error={}".format(response.code, error)
    raise SpacebridgeApiRequestError(error_message)


@defer.inlineCallbacks
def _create_subscription(request_context, subscription, async_kvstore_client):
    # create subscription and return _key
    response = yield async_kvstore_client.async_kvstore_post_request(
        collection=SUBSCRIPTIONS_COLLECTION_NAME,
        data=subscription.to_json(),
        auth_header=request_context.auth_header)

    if response.code == http.OK or response.code == http.CREATED or response.code == http.CONFLICT:
        LOGGER.debug("Subscription Created. subscription_id=%s, expired_time=%s",
                     subscription.key(), subscription.expired_time)
        defer.returnValue(subscription)
    else:
        error = yield response.text()
        error_message = "Failed to create Subscription. status_code={}, error={}".format(response.code, error)
        raise SpacebridgeApiRequestError(error_message)


@defer.inlineCallbacks
def _create_subscription_credentials(request_context, auth, async_kvstore_client):
    # create subscription and return _key
    response = yield async_kvstore_client.async_kvstore_post_request(
        owner=request_context.current_user,
        collection=SUBSCRIPTION_CREDENTIALS_COLLECTION_NAME,
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


@defer.inlineCallbacks
def fetch_session_key_and_type(request_context, async_splunk_client):
    """
    Function that returns session_key and session_key type
    :param request_context:
    :param async_splunk_client:
    """
    if isinstance(request_context.auth_header, JWTAuthHeader):
        LOGGER.debug("JWTAuthHeader detected. Setting session_key_type = {}".format(JWT_TOKEN_TYPE))
        session_key_type = JWT_TOKEN_TYPE
        session_key = request_context.auth_header.token
    else:
        LOGGER.debug("SplunkAuthHeader detected. Setting session_key_type = {}".format(SPLUNK_SESSION_TOKEN_TYPE))
        session_key_type = SPLUNK_SESSION_TOKEN_TYPE
        try:
            session_key = yield get_splunk_cookie(request_context=request_context,
                                                  async_splunk_client=async_splunk_client,
                                                  username=request_context.auth_header.username,
                                                  password=request_context.auth_header.password)
        except Exception:
            # remove after figuring out why auth_header.username errors out above
            session_key = 'fubar'

    defer.returnValue((session_key, session_key_type))


@defer.inlineCallbacks
def create_subscription(request_context,
                        ttl_seconds,
                        search_key,
                        shard_id,
                        async_splunk_client,
                        async_kvstore_client,
                        visualization_id,
                        id_gen=uuid4
                        ):
    """
    Create a visualization subscription object in kvstore collection [subscriptions]
    :param request_context:
    :param ttl_seconds:
    :param search_key:
    :param async_splunk_client:
    :param async_kvstore_client:
    :return:
    """
    # extract params for subscription
    subscription_id = str(id_gen())

    device_id = request_context.device_id
    expiration_time = get_expiration_timestamp_str(ttl_seconds=ttl_seconds)

    if isinstance(request_context.auth_header, JWTAuthHeader):
        LOGGER.debug("JWTAuthHeader detected. Setting session_key_type = %s", JWT_TOKEN_TYPE)
        session_type = JWT_TOKEN_TYPE
        session_key = request_context.auth_header.token
    else:
        LOGGER.debug("SplunkAuthHeader detected. Setting session_key_type = %s", SPLUNK_SESSION_TOKEN_TYPE)
        session_type = SPLUNK_SESSION_TOKEN_TYPE
        session_key = yield get_splunk_cookie(request_context=request_context,
                                              async_splunk_client=async_splunk_client,
                                              username=request_context.auth_header.username,
                                              password=request_context.auth_header.password)

    now = get_current_timestamp_str()

    # Create Subscription object
    subscription = Subscription(_key=subscription_id,
                                ttl_seconds=ttl_seconds,
                                device_id=device_id,
                                subscription_key=search_key,
                                expired_time=expiration_time,
                                shard_id=shard_id,
                                user=request_context.current_user,
                                visualization_id=visualization_id,
                                last_update_time=now)

    auth = SubscriptionCredential(subscription_id=subscription_id,
                                  session_key=session_key,
                                  session_type=session_type,
                                  shard_id=request_context.shard_id,
                                  last_update_time=now,
                                  _key=subscription_id)

    results = yield defer.DeferredList([
        _create_subscription(request_context, subscription, async_kvstore_client),
        _create_subscription_credentials(request_context, auth, async_kvstore_client)
    ], consumeErrors=True)

    for (success, result) in results:
        if not success:
            defer.returnValue(result)

    LOGGER.debug("Subscription created. subscription_id=%s, search_key=%s", subscription_id, search_key)
    defer.returnValue(subscription_id)


@defer.inlineCallbacks
def process_unsubscribe_request(request_context,
                                client_single_subscription=None,
                                server_subscription_response=None,
                                async_kvstore_client=None):
    """
    Process and unsubscribe request, will delete the subscription give the subscription_id from kv store
    :param request_context:
    :param client_single_subscription:
    :param server_subscription_response:
    :param async_kvstore_client:
    :return:
    """
    # Populate response fields
    subscription_id = client_single_subscription.clientUnsubscribeRequest.subscriptionId
    server_subscription_response.subscriptionId = subscription_id
    LOGGER.debug('Start process_unsubscribe_request subscription_id=%s', subscription_id)

    response = yield async_kvstore_client.async_kvstore_delete_request(
        collection=SUBSCRIPTIONS_COLLECTION_NAME,
        key_id=subscription_id,
        owner=NOBODY,
        auth_header=request_context.auth_header)

    # If error case
    if response.code == http.NOT_FOUND:
        # Treat 404s as a deletion as the end result is the same but log it
        error = yield response.text()
        LOGGER.debug("Subscription Id not found. status_code={}, error={}, subscription_id={}"
                     .format(response.code, error, subscription_id))
    elif response.code >= http.INTERNAL_SERVER_ERROR:
        error = yield response.text()
        LOGGER.warn("Failed to unsubscribe. status_code={}, error={}, subscription_id={}"
                    .format(response.code, error, subscription_id))
        raise SpacebridgeApiRequestError(error)
    elif response.code != http.OK:
        error = yield response.text()
        LOGGER.debug("Failed to unsubscribe. status_code=%s, error=%s, subscription_id=%s",
                     response.code, error, subscription_id)
        raise SpacebridgeApiRequestError(error)
    else:
        LOGGER.debug("Finished process_unsubscribe_request subscription_id={}"
                     .format(subscription_id))

    server_subscription_response.serverUnsubscribeResponse.SetInParent()


@defer.inlineCallbacks
def _fetch_ping_data(request_context, subscription_id, async_kvstore_client):
    # See if subscription_id exists in KVStore
    subscription_get_response = yield async_kvstore_client.async_kvstore_get_request(
        collection=SUBSCRIPTIONS_COLLECTION_NAME,
        key_id=subscription_id,
        auth_header=request_context.auth_header)

    credential_get_response = yield async_kvstore_client.async_kvstore_get_request(
        collection=SUBSCRIPTION_CREDENTIALS_COLLECTION_NAME,
        key_id=subscription_id,
        owner=request_context.current_user,
        auth_header=request_context.auth_header
    )

    if subscription_get_response.code != http.OK:
        error = yield subscription_get_response.text()
        LOGGER.debug("Ping failed, subscription get failed status_code=%s, error=%s, subscription_id=%s",
                     subscription_get_response.code, error, subscription_id)
        raise OperationHaltedError()

    subscription_json = yield subscription_get_response.json()
    subscription = Subscription.from_json(subscription_json)

    if credential_get_response.code != http.OK:
        error = yield subscription_get_response.text()
        LOGGER.debug("Ping failed, credential get failed status_code=%s, error=%s, subscription_id=%s",
                     credential_get_response.code, error, subscription_id)
        raise OperationHaltedError()

    credential_json = yield credential_get_response.json()
    credential = SubscriptionCredential.from_json(credential_json)

    defer.returnValue((subscription, credential))


@defer.inlineCallbacks
def _refresh_credential(request_context, subscription_id, credential, async_splunk_client, async_kvstore_client):
    if isinstance(request_context.auth_header, JWTAuthHeader):
        LOGGER.debug("JWTAuthHeader detected. Not updating credentials, subscription_id=%s", subscription_id)
    else:
        LOGGER.debug("Updating credentials, subscription_id=%s", subscription_id)
        temporary_session_key = yield get_splunk_cookie(request_context=request_context,
                                                        async_splunk_client=async_splunk_client,
                                                        username=request_context.auth_header.username,
                                                        password=request_context.auth_header.password)

        credential.session_key = temporary_session_key
        credential.last_update_time = get_current_timestamp_str()

        credential_post_response = yield async_kvstore_client.async_kvstore_post_request(
            collection=SUBSCRIPTION_CREDENTIALS_COLLECTION_NAME,
            data=credential.to_json(),
            owner=request_context.current_user,
            key_id=subscription_id,
            auth_header=request_context.auth_header
        )

        if credential_post_response.code != http.OK:
            error_message = yield credential_post_response.text()
            LOGGER.debug("Failed to update subscription credential. status_code=%s, error=%s, subscription_id=%s",
                         credential_post_response.code, error_message, subscription_id)
            raise SpacebridgeApiRequestError(error_message, status_code=credential_post_response.code)


@defer.inlineCallbacks
def _update_subscription_expiration(request_context, subscription_id, subscription, async_kvstore_client):
    subscription.expired_time = get_expiration_timestamp_str(ttl_seconds=subscription.ttl_seconds)
    subscription.last_update_time = get_current_timestamp_str()
    LOGGER.debug("Touching subscription, subscription_id=%s, last_update_time=%s, expired_time=%s",
                 subscription_id, subscription.last_update_time, subscription.expired_time)

    # Update the subscription with the new expiration_time
    subscription_post_response = yield async_kvstore_client.async_kvstore_post_request(
        collection=SUBSCRIPTIONS_COLLECTION_NAME,
        data=subscription.to_json(),
        key_id=subscription_id,
        auth_header=request_context.auth_header)

    if subscription_post_response.code != http.OK:
        error = yield subscription_post_response.text()
        LOGGER.debug("Failed to update expiration_time. status_code=%s, error=%s, subscription_id=%s",
                     subscription_post_response.code, error, subscription_id)
        raise OperationHaltedError()


@defer.inlineCallbacks
def _extend_subscription(request_context, subscription_id, async_splunk_client, async_kvstore_client):
    LOGGER.debug('Start process_ping_request subscription_id=%s', subscription_id)
    (subscription, credential) = yield _fetch_ping_data(request_context, subscription_id, async_kvstore_client)

    yield _refresh_credential(request_context, subscription_id, credential, async_splunk_client, async_kvstore_client)
    yield _update_subscription_expiration(request_context, subscription_id, subscription, async_kvstore_client)

    defer.returnValue(subscription)


@defer.inlineCallbacks
def process_ping_request(request_context,
                         client_single_subscription=None,
                         server_subscription_ping=None,
                         async_client_factory=None):
    """
    Process a subscription ping request, ping_request don't return any responses
    :param request_context:
    :param client_single_subscription:
    :param server_subscription_ping: Server subscription ping that will be sent back as a response
    :param async_client_factory:
    :return:
    """

    # async clients
    async_splunk_client = async_client_factory.splunk_client()
    async_kvstore_client = async_client_factory.kvstore_client()

    subscription_id = client_single_subscription.clientSubscriptionPing.subscriptionId

    subscription = yield _extend_subscription(request_context, subscription_id, async_splunk_client,
                                              async_kvstore_client)

    server_subscription_ping.subscriptionId = subscription_id

    LOGGER.debug("Subscription Expiration Time Updated subscription_id=%s, expired_time=%s",
                 subscription_id, subscription.expired_time)


@defer.inlineCallbacks
def process_subscription_post_search(request_context,
                                     subscription,
                                     server_subscription_response=None,
                                     async_kvstore_client=None):
    """
    Process and update request, will update the subscription given the subscription_id from kv store
    :param request_context: Meta data for the request
    :param subscription: SubscriptionUpdate object containing post_search and subscription key
    :param server_subscription_response: Server subscription id that will be sent back as a response
    :param async_kvstore_client: Factory used to create async clients
    :return:
    """

    LOGGER.debug('Start process_subscription_post_search subscription_key={}'.format(subscription.key()))
    post_search_key = subscription.key()

    # Update existing subscription_id, otherwise create a new key if not found
    # This code is written with the assumption that update will happen more often than create
    post_response = yield async_kvstore_client.async_kvstore_post_request(
        collection=SEARCH_UPDATES_COLLECTION_NAME,
        data=subscription.to_json(),
        key_id=post_search_key,
        owner=NOBODY,
        auth_header=request_context.auth_header)

    if post_response.code == http.NOT_FOUND:
        post_response = yield async_kvstore_client.async_kvstore_post_request(
            collection=SEARCH_UPDATES_COLLECTION_NAME,
            data=subscription.to_json(),
            owner=NOBODY,
            auth_header=request_context.auth_header)

    if post_response.code not in [http.OK, http.CREATED]:
        error = yield post_response.text()
        error_message = "Failed to update post_search. status_code={}, error={}, subscription_key={}" \
            .format(post_response.code, error, post_search_key)
        raise SpacebridgeApiRequestError(error_message, status_code=post_response.code)

    server_subscription_response.subscriptionId = post_search_key
    server_subscription_response.serverSubscribeResponse.postSearch = subscription.get_post_search()

    LOGGER.debug("Subscription Post Search Updated subscription_key={}, post_search={}"
                 .format(post_search_key, subscription.post_search))
