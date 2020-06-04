"""
(C) 2019 Splunk Inc. All rights reserved.

Module to process NLP Requests
"""

from splapp_protocol import nlp_splapp_request_pb2
from spacebridgeapp.search.saved_search_requests import fetch_saved_search, fetch_saved_searches
from spacebridgeapp.util import constants
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from twisted.internet import defer
from twisted.web import http

import time
import spacebridgeapp.dashboard.parse_data as parse

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_nlp_request_processor.log", "nlp_request_processor")


def compute_latency(time_before):
    return (time.time() - time_before) * 1000.0


@defer.inlineCallbacks
def process_saved_search_sync_request(request_context,
                                      client_single_request,
                                      server_single_response,
                                      async_client_factory):
    """
    This method will create an async http request to the saved search splunk endpoint and return a list of SavedSearchMetaData
    protos in a server_single_response object

    :param request_context:
    :param client_single_request: incoming request
    :param server_single_response: outgoing response
    :param async_client_factory: async client used to make https request
    :return:
    """

    LOGGER.debug("Start populating response for saved search sync request")

    # async clients
    async_splunk_client = async_client_factory.splunk_client()
    async_telemetry_client = async_client_factory.telemetry_client()

    # Measure time taken to execute the request
    time_before = time.time()
    # fetch saved search metadata
    saved_searches = yield fetch_saved_searches(request_context.auth_header, "-", "-", async_splunk_client)

    latency = compute_latency(time_before)
    LOGGER.info("Time Taken request=Saved Searches, execution_time_ms={:0.3f}".format(latency))
    #TODO: send to telemetry

    # populate saved search sync response
    for saved_search in saved_searches:
        saved_search_metadata = nlp_splapp_request_pb2.SavedSearchMetaData()
        saved_search_metadata.id = saved_search.name
        saved_search_metadata.name = saved_search.name
        server_single_response.savedSearchesSyncResponse.savedSearchesMetaData.extend([saved_search_metadata])

    LOGGER.info("Finished populating response for saved search sync request")


@defer.inlineCallbacks
def process_saved_search_get_spl_request(request_context,
                                         client_single_request,
                                         server_single_response,
                                         async_client_factory):
    """
    This method will create an async http request to the saved search endpoint and return saved search spl
    in a server_single_response object

    :param request_context:
    :param client_single_request: incoming request
    :param server_single_response: outgoing response
    :param async_client_factory: async client used to make https request
    :return:
    """

    LOGGER.debug("Start populating response for saved search get spl request")

    ref = client_single_request.savedSearchSPLGetRequest.savedSearchId

    # async clients
    async_splunk_client = async_client_factory.splunk_client()
    async_telemetry_client = async_client_factory.telemetry_client()

    # Measure time taken to execute the request
    time_before = time.time()
    # fetch dashboard bodies
    saved_search = yield fetch_saved_search(request_context.auth_header, "-", "-", ref, async_splunk_client)

    latency = compute_latency(time_before)

    LOGGER.info("Time Taken request=Get Saved Search SPL, execution_time_ms={:0.3f}".format(latency))
    #TODO: send to telemetry similar to send_dashboard_list_request_metrics_to_telemetry

    # populate saved saearch get spl response
    server_single_response.savedSearchSPLGetResponse.spl = saved_search.search

    LOGGER.info("Finished populating response for saved search get spl request")


@defer.inlineCallbacks
def process_dashboards_sync_request(request_context,
                                    client_single_request,
                                    server_single_response,
                                    async_client_factory):
    """
    This method will create an async http request to the ui/views splunk endpoint and return a list of DashboardMetaData
    protos in a server_single_response object

    :param request_context:
    :param client_single_request: incoming request
    :param server_single_response: outgoing response
    :param async_client_factory: async client used to make https request
    :return:
    """

    LOGGER.debug("Start populating response for dashboards sync request")

    # async clients
    async_splunk_client = async_client_factory.splunk_client()
    async_telemetry_client = async_client_factory.telemetry_client()

    # Measure time taken to execute dashboard list request
    time_before = time.time()
    # fetch dashboards metadata
    params = {'output_mode': 'json',
              'sort_dir': 'asc',
              'sort_key': 'label',
              'sort_mode': 'alpha',
              'offset': 0,
              'count': 0}
    response = yield async_splunk_client.async_get_dashboard_list_request(request_context.auth_header, "-", "-", params)

    latency = compute_latency(time_before)
    LOGGER.info("Time Taken request=dashboards, execution_time_ms={:0.3f}".format(latency))

    #TODO: send to telemetry

    if response.code != http.OK:
        response_text = yield response.text()
        raise SpacebridgeApiRequestError("Failed dashboards_sync response.code={}, response.text={}"
                                         .format(response.code, response_text))

    # convert to json object
    response_json = yield response.json()
    entry_json_list = response_json.get('entry')

    # populate dashboards sync response
    for entry_json in entry_json_list:
        if entry_json is not None and isinstance(entry_json, dict):
            dashboard_id = parse.get_string(entry_json.get('id'))
            content = entry_json.get('content')
            if content is not None:
                title = parse.get_string(content.get('label'))

            dashboards_metadata = nlp_splapp_request_pb2.DashboardMetaData()
            dashboards_metadata.id = dashboard_id
            dashboards_metadata.name = title
            server_single_response.dashboardsSyncResponse.dashboardsMetaData.extend([dashboards_metadata])

    LOGGER.info("Finished populating response for dashboards sync request")
