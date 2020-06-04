"""
(C) 2019 Splunk Inc. All rights reserved.

Module for saved search requests
"""

from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from spacebridgeapp.dashboard.parse_search import to_saved_search, to_saved_search_history
from spacebridgeapp.exceptions.error_message_helper import format_splunk_error
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from twisted.internet import defer
from twisted.web import http
from spacebridgeapp.logging import setup_logging

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_subscription_search_requests.log",
                       "subscription_search_requests")


@defer.inlineCallbacks
def fetch_saved_search(auth_header, owner, app_name, ref, async_splunk_client):
    """
    Fetch saved search metadata from ref
    :param auth_header:
    :param owner:
    :param app_name:
    :param ref:
    :param async_splunk_client:
    :return:
    """
    response = yield async_splunk_client.async_get_saved_searches(auth_header=auth_header,
                                                                  owner=owner,
                                                                  app_name=app_name,
                                                                  ref=ref)
    # Log Error and return if unable to query saved search ref
    if response.code != http.OK:
        error = yield response.text()
        LOGGER.error("Failed to query saved search. status_code={}, error={}, ref={}".format(response.code, error, ref))
        raise SpacebridgeApiRequestError(format_splunk_error(response.code, error))

    response_json = yield response.json()
    entry_json_list = response_json.get('entry')
    if entry_json_list:
        saved_search = to_saved_search(entry_json_list[0])
        defer.returnValue(saved_search)

    # raise exception if failed to fetch saved search
    raise SpacebridgeApiRequestError("Unable to fetch saved search.")


@defer.inlineCallbacks
def fetch_saved_searches(auth_header, owner, app_name, async_splunk_client):
    """
    Fetch saved search metadata for all saved searches
    :param auth_header:
    :param owner:
    :param app_name:
    :param async_splunk_client:
    :return:
    """
    response = yield async_splunk_client.async_get_saved_searches(auth_header=auth_header,
                                                                  owner=owner,
                                                                  app_name=app_name,
                                                                  ref="")
    # Log Error and return if unable to get all saved searches
    if response.code != http.OK:
        error = yield response.text()
        LOGGER.error("Failed to get all saved searches. status_code={}, error={}".format(response.code, error))
        raise SpacebridgeApiRequestError(format_splunk_error(response.code, error))

    response_json = yield response.json()
    entry_json_list = response_json.get('entry')
    if entry_json_list:
        saved_searches = []
        for entry in entry_json_list:
            saved_searches.append(to_saved_search(entry))
        defer.returnValue(saved_searches)

    # raise exception if failed to fetch saved search
    raise SpacebridgeApiRequestError("Unable to get all saved searches.")


@defer.inlineCallbacks
def fetch_saved_search_history(auth_header, owner, app_name, ref, async_splunk_client):
    """
    Fetch saved search history given ref
    :param auth_header:
    :param owner:
    :param app_name:
    :param ref:
    :param async_splunk_client:
    :return:
    """
    response = yield async_splunk_client.async_get_saved_searches_history(auth_header=auth_header,
                                                                          owner=owner,
                                                                          app_name=app_name,
                                                                          ref=ref)
    if response.code != http.OK:
        error = yield response.text()
        LOGGER.error("Failed to query saved search history. status_code={}, error={}, ref={}"
                     .format(response.code, error, ref))
        raise SpacebridgeApiRequestError(format_splunk_error(response.code, error))

    response_json = yield response.json()
    entry_json_list = response_json.get('entry')
    if entry_json_list:
        saved_search_history = to_saved_search_history(entry_json_list[0])
        defer.returnValue(saved_search_history)

    # raise exception if failed to fetch saved search history
    raise SpacebridgeApiRequestError("Unable to fetch saved search history.")


@defer.inlineCallbacks
def dispatch_saved_search(auth_header, owner, app_name, ref, data, async_splunk_client):
    """
    Dispatch a saved search query
    :param auth_header:
    :param owner:
    :param app_name:
    :param ref:
    :param data:
    :param async_splunk_client:
    :return:
    """
    response = yield async_splunk_client.async_post_saved_searches_dispatch(auth_header=auth_header,
                                                                            owner=owner,
                                                                            app_name=app_name,
                                                                            ref=ref,
                                                                            data=data)
    if response.code != http.OK and response.code != http.CREATED:
        error = yield response.text()
        LOGGER.error("Failed to create dispatch job saved search. status_code={}, error={}, {}"
                     .format(response.code, error, ref))
        raise SpacebridgeApiRequestError(format_splunk_error(response.code, error))

    response_json = yield response.json()
    defer.returnValue(response_json.get("sid"))
