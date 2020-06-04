"""
(C) 2019 Splunk Inc. All rights reserved.

Subscription asynchronous processor methods

"""
from cloudgateway.splunk.auth import SplunkAuthHeader
from spacebridgeapp.data.dispatch_state import DispatchState
from spacebridgeapp.request.dashboard_request_processor import fetch_search_job_results_visualization_data, \
    get_search_job_content
from spacebridgeapp.dashboard.dashboard_helpers import parse_dashboard_id
from spacebridgeapp.request.request_processor import JWTAuthHeader
from spacebridgeapp.subscriptions.subscription_search_requests import build_subscription_update, \
    send_subscription_updates, start_job_and_update_search, fetch_visualization_data, update_search, update_job_status, \
    fetch_search
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, JWT_TOKEN_TYPE
from spacebridgeapp.subscriptions.subscription_requests import fetch_subscriptions, count_dependant_searches
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.data.visualization_type import VisualizationType
from spacebridgeapp.data.dashboard_data import DashboardVisualizationId
from spacebridgeapp.search.input_token_support import inject_tokens_into_string, load_input_tokens
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.time_utils import is_datetime_expired, get_current_timestamp_str
from twisted.internet import defer

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_subscription_processor.log", "subscription_processor")


@defer.inlineCallbacks
def _update_subscriptions_with_post_search(auth_header, subscription_search, subscriptions, input_tokens,
                                           encryption_context, job_status, async_spacebridge_client,
                                           async_kvstore_client, async_splunk_client, post_search_map):
    for subscription in subscriptions:
        post_search = post_search_map.get(subscription.key(), None)
        try:
            current_results = yield fetch_visualization_data(auth_header=auth_header,
                                                             owner=subscription_search.owner,
                                                             app_name=SPACEBRIDGE_APP_NAME,
                                                             subscription_search=subscription_search,
                                                             input_tokens=input_tokens,
                                                             async_splunk_client=async_splunk_client,
                                                             map_post_search=post_search)

        except SpacebridgeApiRequestError as e:

            LOGGER.error("Failed to fetch visualization data with post search, update cannot be sent, error={}"
                         .format(e.message))
            defer.returnValue(False)

        LOGGER.debug("Search results={}".format(current_results))
        subscription_update = build_subscription_update(subscription_search, current_results, job_status)

        yield send_subscription_updates(auth_header=auth_header,
                                        subscriptions=[subscription],  # Wrap in a list
                                        subscription_update=subscription_update,
                                        encryption_context=encryption_context,
                                        async_spacebridge_client=async_spacebridge_client,
                                        async_kvstore_client=async_kvstore_client)

    defer.returnValue(True)


@defer.inlineCallbacks
def _update_subscriptions_without_post_search(auth_header, subscription_search, input_tokens,
                                              encryption_context, job_status, async_spacebridge_client,
                                              async_kvstore_client, async_splunk_client,
                                              subscriptions):
    if subscriptions:
        try:
            current_results = yield fetch_visualization_data(auth_header=auth_header,
                                                             owner=subscription_search.owner,
                                                             app_name=SPACEBRIDGE_APP_NAME,
                                                             subscription_search=subscription_search,
                                                             input_tokens=input_tokens,
                                                             async_splunk_client=async_splunk_client)
        except SpacebridgeApiRequestError as e:
            LOGGER.error("Failed to fetch visualization data, update cannot be sent, error={}".format(e.message))
            defer.returnValue(False)

        LOGGER.debug("Search sid=%s, results=%s", subscription_search.key(), current_results)
        subscription_update = build_subscription_update(subscription_search, current_results, job_status)

        yield send_subscription_updates(auth_header=auth_header,
                                        subscriptions=subscriptions,
                                        subscription_update=subscription_update,
                                        encryption_context=encryption_context,
                                        async_spacebridge_client=async_spacebridge_client,
                                        async_kvstore_client=async_kvstore_client)

    defer.returnValue(True)


@defer.inlineCallbacks
def _broadcast_data_update(auth_header, subscription_search, subscriptions, search_updates,
                           input_tokens, encryption_context, job_status, async_spacebridge_client,
                           async_kvstore_client, async_splunk_client):

    visualization_type = VisualizationType.from_value(subscription_search.visualization_type)
    if visualization_type == VisualizationType.DASHBOARD_VISUALIZATION_MAP:
        subscriptions_with_post_searches = {key for key in search_updates}
        post_search_map = {key: search_updates[key].get_post_search() for key in subscriptions_with_post_searches}

        yield _update_subscriptions_with_post_search(auth_header=auth_header,
                                                     subscription_search=subscription_search,
                                                     subscriptions=subscriptions,
                                                     input_tokens=input_tokens,
                                                     encryption_context=encryption_context,
                                                     job_status=job_status,
                                                     async_spacebridge_client=async_spacebridge_client,
                                                     async_kvstore_client=async_kvstore_client,
                                                     async_splunk_client=async_splunk_client,
                                                     post_search_map=post_search_map)
    else:
        yield _update_subscriptions_without_post_search(auth_header=auth_header,
                                                        subscription_search=subscription_search,
                                                        input_tokens=input_tokens,
                                                        encryption_context=encryption_context,
                                                        job_status=job_status,
                                                        async_spacebridge_client=async_spacebridge_client,
                                                        async_kvstore_client=async_kvstore_client,
                                                        async_splunk_client=async_splunk_client,
                                                        subscriptions=subscriptions)

    defer.returnValue(True)


def _to_auth_header(credentials):
    auth_header = SplunkAuthHeader(credentials.session_key)
    if credentials.session_type == JWT_TOKEN_TYPE:
        auth_header = JWTAuthHeader(credentials.user, credentials.session_key)

    return auth_header


@defer.inlineCallbacks
def _refresh_search_job(subscription_search, user_subscriptions, credentials, input_tokens,
                        async_splunk_client, async_kvstore_client):
    try:
        # we need a user to run the search.  If the rest of the code is working properly,
        # all subscribers to a search share the same roles.
        subscription_id, credentials = next(iter(credentials.items()))
        user_auth_header = _to_auth_header(credentials)

        yield start_job_and_update_search(user_auth_header, subscription_search, input_tokens, credentials.user,
                                          async_splunk_client, async_kvstore_client)
    except StopIteration:
        LOGGER.info("Failed to start search job, credentials missing. search_key=%s",
                    subscription_search.key())
    except SpacebridgeApiRequestError:
        LOGGER.exception("Failed to start search job, search_key=%s", subscription_search.key())

    defer.returnValue(True)


@defer.inlineCallbacks
def _refresh_search_job_if_expired(subscription_search, user_subscriptions, credentials, input_tokens,
                                   async_splunk_client, async_kvstore_client):
    if subscription_search.is_refreshing() and is_datetime_expired(subscription_search.next_update_time):
        LOGGER.debug("Refresh time has passed, start new search job, search_key=%s", subscription_search.key())

        yield _refresh_search_job(subscription_search, user_subscriptions, credentials, input_tokens,
                                  async_splunk_client, async_kvstore_client)

    defer.returnValue(True)


_COMPLETED_DISPATCH = [DispatchState.DONE.value, DispatchState.FAILED.value]


@defer.inlineCallbacks
def _handle_expired_sid(system_auth_header, subscription_search, user_subscriptions, credentials, input_tokens,
                        async_splunk_client, async_kvstore_client):
    LOGGER.info("Job status not found, search_key=%s", subscription_search.key())
    yield _refresh_search_job(subscription_search, user_subscriptions, credentials, input_tokens,
                              async_splunk_client, async_kvstore_client)

    job_status = yield get_search_job_content(system_auth_header, subscription_search.owner, SPACEBRIDGE_APP_NAME,
                                              subscription_search.sid, async_splunk_client)

    defer.returnValue(job_status)


@defer.inlineCallbacks
def process_pubsub_subscription(system_auth_header, encryption_context, async_spacebridge_client,
                                async_kvstore_client, async_splunk_client, search_context):
    """
    :param system_auth_header:
    :param encryption_context:
    :param async_spacebridge_client:
    :param async_kvstore_client:
    :param async_splunk_client:
    :param search_context:
    :return:
    """
    subscription_search = search_context.search

    credentials = search_context.subscription_credentials

    subscriptions = search_context.subscriptions

    search_updates = search_context.search_updates

    user_subscriptions = [sub for sub in subscriptions if sub.key() in credentials]

    LOGGER.debug(
        "Found valid subscribers, search_key=%s, total_subscriber_count=%s, user_subscriber_count=%s, search_updates=%s",
        subscription_search.key(),
        len(subscriptions),
        len(user_subscriptions),
        search_updates)

    input_tokens = load_input_tokens(subscription_search.input_tokens)

    if not subscription_search.sid:
        LOGGER.info("Pubsub search has no sid, search_key=%s", subscription_search.key())
        defer.returnValue(False)

    job_status = yield get_search_job_content(system_auth_header, subscription_search.owner, SPACEBRIDGE_APP_NAME,
                                              subscription_search.sid, async_splunk_client)

    LOGGER.debug("Search job status, search_key=%s, job=%s", subscription_search.key(), job_status)

    dependant_search_count = yield count_dependant_searches(system_auth_header, subscription_search.key(),
                                                            async_kvstore_client)

    LOGGER.debug("Search job dependendants search_key=%s, user_subscriptions=%s, depdendant_search_count=%s",
                 subscription_search.key(), len(user_subscriptions), dependant_search_count)
    if not job_status and (len(user_subscriptions) > 0 or dependant_search_count > 0):
        job_status = yield _handle_expired_sid(system_auth_header, subscription_search, user_subscriptions,
                                               credentials, input_tokens,
                                               async_splunk_client, async_kvstore_client)

    if not job_status:
        LOGGER.warn("Job status could not be retrieved, search_key=%s, sid=%s",
                    subscription_search.key(), subscription_search.sid)
        defer.returnValue(False)

    # only send updates if the job was still running the last time we saw it
    if len(user_subscriptions) > 0:
        LOGGER.debug("Broadcast Data Updates: search_key=%s, updates=%s", subscription_search.key(), search_updates)
        yield _broadcast_data_update(system_auth_header, subscription_search, user_subscriptions, search_updates,
                                     input_tokens, encryption_context, job_status,
                                     async_spacebridge_client, async_kvstore_client, async_splunk_client)

    update_job_status(subscription_search, job_status)

    if len(user_subscriptions) > 0 or dependant_search_count > 0:
        LOGGER.debug("Search has subscribers search_key=%s, subscriber_count=%s, dependant_search_count=%s",
                     subscription_search.key(), len(user_subscriptions), dependant_search_count)

        yield _refresh_search_job_if_expired(subscription_search, user_subscriptions, credentials, input_tokens,
                                             async_splunk_client, async_kvstore_client)

        subscription_search.last_update_time = get_current_timestamp_str()

    LOGGER.debug("Persisting search job state, search_key=%s, job_status=%s",
                 subscription_search.key(), job_status)
    yield update_search(system_auth_header, subscription_search, async_kvstore_client)

    defer.returnValue(True)


@defer.inlineCallbacks
def process_subscription(request_context=None,
                         subscription_id=None,
                         server_subscription_update=None,
                         async_client_factory=None,
                         guid_generator=None,
                         map_post_search=None):
    """
    Process subscription given subscription_id.  This will populate a server_subscription_update with data if
    subscription saved data exists.

    :param request_context:
    :param subscription_id:
    :param server_subscription_update:
    :param async_client_factory:
    :param guid_generator:
    :param map_post_search:
    :return:
    """
    # Pull out async_kvstore_client
    async_kvstore_client = async_client_factory.kvstore_client()

    # Make KVStore call to the subscription and pull out device_id, search_key, check expired?
    subscriptions = yield fetch_subscriptions(auth_header=request_context.auth_header,
                                              subscription_id=subscription_id,
                                              async_kvstore_client=async_kvstore_client)
    # list of subscriptions returned
    if not subscriptions:
        error_message = "Failed to fetch subscription. subscription_id={}".format(subscription_id)
        raise SpacebridgeApiRequestError(error_message)

    # Get first subscription
    subscription = subscriptions[0]

    # Make KVStore call with search_key to fetch the search
    search = yield fetch_search(request_context.auth_header,
                                search_key=subscription.subscription_key,
                                async_kvstore_client=async_kvstore_client)

    LOGGER.debug("Retrieved search.  search_key=%s, search=%s", subscription.subscription_key, search)

    # Pull out async_splunk_client
    async_splunk_client = async_client_factory.splunk_client()

    # if sid from search exists then return a ServerSubscriptionUpdate with data from sid if finished processing
    if search and search.sid:
        LOGGER.debug("Search job found, search_key=%s, sid=%s", subscription.subscription_key, search.sid)
        yield process_single_subscription_update(request_context=request_context,
                                                 search=search,
                                                 visualization_id=subscription.visualization_id,
                                                 server_subscription_update=server_subscription_update,
                                                 async_splunk_client=async_splunk_client,
                                                 guid_generator=guid_generator,
                                                 map_post_search=map_post_search)
    else:
        LOGGER.debug("Search not found, search_key=%s, sid=%s", subscription.subscription_key, search.sid)


@defer.inlineCallbacks
def process_single_subscription_update(request_context,
                                       search,
                                       visualization_id,
                                       server_subscription_update,
                                       async_splunk_client,
                                       guid_generator,
                                       map_post_search=None):
    """
    An async processor which will create a subscription data event
    :param request_context:
    :param search:
    :param visualization_id:
    :param server_subscription_update:
    :param async_splunk_client:
    :param guid_generator:
    :return:
    """
    user, app_name, dashboard_name = parse_dashboard_id(search.dashboard_id)

    # Add post_search if search is dependent (i.e. defines a base)

    post_search = None
    sid = search.sid
    if search.base:
        input_tokens = load_input_tokens(search.input_tokens)
        post_search = inject_tokens_into_string(input_tokens, search.query)
        LOGGER.debug("Search has base, using parent sid, search_key=%s, sid=%s, post_search=%s",
                     search.key(), sid, post_search)

    if not post_search:
        post_search = map_post_search
    elif map_post_search:
        post_search += " " + map_post_search

    # Query the job status
    job_status = yield get_search_job_content(auth_header=request_context.system_auth_header,
                                              owner=user,
                                              app_name=app_name,
                                              search_id=sid,
                                              async_splunk_client=async_splunk_client)

    # If no job_status we don't try to send this update
    if job_status:
        # call api with sid
        visualization_data = yield fetch_search_job_results_visualization_data(
            owner=user,
            app_name=app_name,
            search_id=sid,
            post_search=post_search,
            auth_header=request_context.system_auth_header,
            async_splunk_client=async_splunk_client)

        # populate update if data available, if no data is available it means job is still processing or error occurred
        # its okay if we miss this update as it should get processing in looping update
        if visualization_data:
            # Populate the server_subscription_update
            LOGGER.debug("Post processing sid=%s, visualization_id=%s", sid, visualization_id)
            dashboard_visualization_id = DashboardVisualizationId(dashboard_id=search.dashboard_id,
                                                                  visualization_id=visualization_id)

            # Set params
            server_subscription_update.updateId = guid_generator()
            visualization_data.set_protobuf(server_subscription_update.dashboardVisualizationEvent.visualizationData)

            # Update update with search job state,
            if job_status:
                server_subscription_update.dashboardVisualizationEvent.dispatchState = int(job_status.dispatch_state)
                server_subscription_update.dashboardVisualizationEvent.doneProgress = float(job_status.done_progress)

            # Update with dashboard_visualization_id
            dashboard_visualization_id.set_protobuf(
                server_subscription_update.dashboardVisualizationEvent.dashboardVisualizationId)
        else:
            LOGGER.debug("No visualization data found, sid=%s, visualization_id=%s", sid, visualization_id)
    else:
        LOGGER.debug("No search job status found, sid=%s, visualization_id=%s", sid, visualization_id)

