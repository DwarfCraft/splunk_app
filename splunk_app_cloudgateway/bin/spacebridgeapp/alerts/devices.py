"""
(C) 2019 Splunk Inc. All rights reserved.
"""

import sys
import os
from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'lib']))
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

import json
from spacebridgeapp.util.constants import ALERT_RECIPIENTS, CONFIGURATION, ALL_USERS
from spacebridgeapp.util import constants
from twisted.internet import defer
from twisted.web import http
from spacebridgeapp.logging import setup_logging
LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + '_mobile_alert.log', 'mobile_alert')


@defer.inlineCallbacks
def get_registered_devices(request_context, async_kvstore_client, alert_payload):
    """
    Fetch all registered devices for all users asynchronously across users
    :param session_key:
    :param async_kvstore_client:
    :return: List of device ids
    """
    configuration = alert_payload[CONFIGURATION]

    # If all users is selected
    if configuration and ALERT_RECIPIENTS in configuration.keys() and configuration[ALERT_RECIPIENTS] == ALL_USERS:
        LOGGER.info("getting devices for all users")
        users = yield fetch_devices(request_context, async_kvstore_client)
        defer.returnValue(users)

    # if a specific role is selected
    elif configuration and ALERT_RECIPIENTS in configuration.keys():
        role = configuration[ALERT_RECIPIENTS]
        LOGGER.info("getting users for role=%s" % str(role))
        try:
            users = yield fetch_devices(request_context, async_kvstore_client, role=role)
            defer.returnValue(users)
        except Exception:
            LOGGER.exception("Unexpected expectation getting registered devices")

    # If nothing is selected, return an empty list
    else:
        defer.returnValue([])


@defer.inlineCallbacks
def fetch_devices(request_context, async_kvstore_client, role=None):
    """
    Given a role, fetch all devices reigstered to users belonging to given role. If no role is specified, fetch all
    devices
    """
    LOGGER.info("fetching devices by role=%s" % str(role))
    params = build_query_params(role)

    response = yield async_kvstore_client.async_kvstore_get_request(constants.DEVICE_ROLES_COLLECTION_NAME,
                                                              auth_header=request_context.auth_header,
                                                              params=params)

    if response.code == http.OK:
        jsn = yield response.json()
        if type(jsn) == list and len(jsn) > 0:
            most_recent_timestamp = jsn[0][constants.TIMESTAMP]
            result = set([row[constants.REGISTERED_DEVICES_DEVICE_ID] for row in jsn if row[constants.TIMESTAMP] == most_recent_timestamp])
            defer.returnValue(result)

    text = yield response.text()
    LOGGER.info("Received empty or unsuccessful response from kvstore with response.code=%s, %s" % (str(response.code), str(text)))
    defer.returnValue(set())


def build_query_params(role):


    params = {constants.SORT: "%s:%d" % (constants.TIMESTAMP, -1)}

    if role:
        query = {constants.ROLE:role}
        params[constants.QUERY] = json.dumps(query)

    return params
