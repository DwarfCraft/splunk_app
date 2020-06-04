"""
(C) 2019 Splunk Inc. All rights reserved.

Module for any requests that will return the raw json
"""
from twisted.internet import defer
from twisted.web import http
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from spacebridgeapp.logging.spacebridge_logging import setup_logging
from spacebridgeapp.dashboard.dashboard_helpers import generate_search_str
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_dashboard_request_json.log",
                       "dashboard_request_json")


@defer.inlineCallbacks
def fetch_dashboard_list_json(request_context,
                              offset=0,
                              max_results=0,
                              app_names=[],
                              dashboard_ids=[],
                              async_splunk_client=None):
    """
    Fetch the dashboard list json Splunk api /data/ui/views
    :param request_context:
    :param offset:
    :param max_results:
    :param app_names:
    :param dashboard_ids:
    :param async_splunk_client:
    :return:
    """
    search_str = generate_search_str(app_names, dashboard_ids, request_context.current_user)
    params = {'output_mode': 'json',
              'search': search_str,
              'sort_dir': 'asc',
              'sort_key': 'label',
              'sort_mode': 'alpha',
              'offset': offset,
              'count': max_results}

    # Don't specify owner, defaults to '-' which will retrieve dashboards from all users visible for current_user
    response = yield async_splunk_client.async_get_dashboard_list_request(auth_header=request_context.auth_header,
                                                                          params=params)

    LOGGER.info('fetch_dashboard_list_json response={}'.format(response.code))

    if response.code != http.OK:
        response_text = yield response.text()
        raise SpacebridgeApiRequestError("Failed fetch_dashboard_list_json response.code={}, response.text={}"
                                         .format(response.code, response_text))

    response_json = yield response.json()
    defer.returnValue(response_json)

