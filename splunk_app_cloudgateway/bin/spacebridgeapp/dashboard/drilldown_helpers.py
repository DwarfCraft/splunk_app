"""
(C) 2019 Splunk Inc. All rights reserved.

Module for drilldown helper functions
"""
import sys
from twisted.internet import defer
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.dashboard.dashboard_request_json import fetch_dashboard_list_json
from spacebridgeapp.dashboard.dashboard_helpers import shorten_dashboard_id_from_url, parse_dashboard_id, \
    generate_dashboard_id

if sys.version_info < (3, 0):
    from urlparse import urlparse, parse_qsl

else:
    from urllib.parse import urlparse, parse_qsl

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_drilldown_helpers.log", "drilldown_helpers")

FORM_PREFIX = "form."
SPLUNK_URL_PREFIX = '/app/'


def parse_dashboard_link(url=None):
    """
    Helper to parse dashboard_id and input_map from drilldown link
    :param url:
    :return:
    """
    dashboard_id = ''
    input_map = {}

    if url and url.startswith(SPLUNK_URL_PREFIX):
        parsed_url = urlparse(url)
        if parsed_url.path:
            # We can just use the url path here because the fetch_dashboard_list_json ignores user
            owner, app_name, dashboard_name = parse_dashboard_id(parsed_url.path[1:]) # removes the '/' from /app url
            try:
                dashboard_id = generate_dashboard_id("-", app_name, dashboard_name)
            except SpacebridgeApiRequestError as e:
                LOGGER.error("Failed to parse dashboard link url={}, {}".format(url, e.message))
        if parsed_url.query:
            input_map = query_params_to_input_map(parsed_url.query)

        if not dashboard_id or not input_map:
            LOGGER.error("Failed to get dashboard_id=%s or input_map=%s", dashboard_id, input_map)

    LOGGER.debug("Parse dashboard_link url={}, dashboard_id={}, input_map={}".format(url, dashboard_id, input_map))
    return_tuple = (dashboard_id, input_map)
    return return_tuple


def query_params_to_input_map(query_params):
    """
    Helper to convert a query_params string to an input_map
    :param query_params:
    :return:
    """
    if query_params:
        input_list = parse_qsl(query_params)
        # we will strip the "form." prefix from keys when we pass back to client
        input_map = {key[len(FORM_PREFIX):] if key.startswith(FORM_PREFIX) else key: value for key, value in input_list}
        return input_map
    return {}
