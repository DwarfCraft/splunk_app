"""
(C) 2019 Splunk Inc. All rights reserved.

Module to process requests related to Jubilee
"""

from twisted.internet import defer
from twisted.web import http
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.request.request_processor import get_splunk_cookie

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_jubilee_request_processor.log", "jubilee_request_processor")


@defer.inlineCallbacks
def process_jubilee_connection_info_request(request_context,
                                            client_single_request,
                                            server_single_response,
                                            async_splunk_client,
                                            async_jubilee_client):
    """
    Process requests for fetching jubilee connection information which consists of a splunk cookie, api key and
    hostname

    :param request_context:
    :param client_single_request: clientSingleRequest Proto of type jubileConnectionInfoRequest
    :param server_single_response: serverSingleResponse proto which is the container for the response
    :param async_splunk_client [AsyncSplunkClient]
    :param async_jubilee_client [AsyncJubileeClient]
    :return: None (populates server_single_response)
    """

    yield populate_jubilee_connection_info_response(request_context, client_single_request, server_single_response,
                                                    async_splunk_client, async_jubilee_client)


@defer.inlineCallbacks
def populate_jubilee_connection_info_response(request_context, client_single_request,
                                              server_single_response, async_splunk_client, async_jubilee_client):
    """
    Populates jubilee connection information in the server_single_response proto by first getting splunk_cookie
    from splunk and then using that cookie to fetch jubilee's hostname and api_key.
    """

    LOGGER.info("start populating response for jubilee connection info request")
    username = request_context.auth_header.username
    password = request_context.auth_header.password
    splunk_cookie = yield get_splunk_cookie(request_context, async_splunk_client, username, password)
    api_key = yield get_api_key(request_context, async_jubilee_client, splunk_cookie)
    hostname = yield get_hostname(request_context, async_jubilee_client, splunk_cookie)
    populate_response(server_single_response, client_single_request, splunk_cookie, hostname, api_key)

    LOGGER.info("finished populating response for jubilee connection info request")


def populate_response(server_single_response, client_single_request, splunk_cookie, hostname, api_key):
    """
    Populates the serverSingleResponse proto with the jubileeConnectionInfoResponse field

    :param server_single_response: serverSingleResponse proto
    :param client_single_request: clientSingleRequest proto
    :param splunk_cookie: splunk cookie returned by /auth/login api
    :param hostname: name of jubilee host
    :param api_key: api key with which to call jubilee api
    :return:
    """
    server_single_response.jubileeConnectionInfoResponse.splunkCookie = splunk_cookie
    server_single_response.jubileeConnectionInfoResponse.apiKey = api_key
    server_single_response.jubileeConnectionInfoResponse.hostname = hostname


@defer.inlineCallbacks
def get_hostname(request_context, async_jubilee_client, splunk_cookie):
    """
    Fetches jubilee's hostname using jubilee's apis
    """
    response = yield async_jubilee_client.async_get_host_name(splunk_cookie, request_context.auth_header)

    if response.code == http.OK:
        jsn = yield response.json()
        defer.returnValue(parse_host_name(jsn))

    else:
        message = yield response.text()
        raise SpacebridgeApiRequestError("Call to fetch jubilee hostname failed with response.code={}, message={}"
                                         .format(response.code, message))


@defer.inlineCallbacks
def get_api_key(request_context, async_jubilee_client, splunk_cookie):
    """
    Fetches api key for jubilee using jubilee's api
    """
    response = yield async_jubilee_client.async_get_api_key(splunk_cookie, request_context.auth_header)

    if response.code == http.OK:
        jsn = yield response.json()
        defer.returnValue(parse_api_key(jsn))

    else:
        message = yield response.text()
        raise SpacebridgeApiRequestError("Call to fetch jubilee api key failed with response.code={}, message={}"
                                         .format(response.code, message))


def parse_api_key(json):
    """
    Helper method to extract api key from response json
    """
    return json["entry"][0]["content"]["api_key"]


def parse_host_name(json):
    """
    Helper method to extract host name from response json
    """
    return json["entry"][0]["content"]["backend_uri"]
