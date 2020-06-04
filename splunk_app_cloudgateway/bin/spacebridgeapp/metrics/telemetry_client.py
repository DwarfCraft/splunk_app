"""
(C) 2019 Splunk Inc. All rights reserved.

Client to send data to the telemetry endpoint
"""

import splunk.rest as rest
from twisted.web import http

from spacebridgeapp.data.telemetry_data import InstallationEnvironment
from spacebridgeapp.util import constants
from spacebridgeapp.util.constants import NOBODY
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, HEADER_AUTHORIZATION, \
    HEADER_CONTENT_TYPE, APPLICATION_JSON
import requests
from spacebridgeapp.rest.clients.async_client import AsyncClient
import json
from spacebridgeapp.logging import setup_logging
import logging
from twisted.internet import defer

from splapp_protocol import request_pb2

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_metrics.log", "metrics", level=logging.WARNING)

OPT_IN_VERSION = 3


def get_telemetry_uri():
    rest_uri = rest.makeSplunkdUri()
    return '%sservicesNS/%s/%s/telemetry-metric' % (
        rest_uri,
        NOBODY,
        SPACEBRIDGE_APP_NAME
    )


def create_telemetry_payload(event):
    return {
        "type": "event",
        "component": SPACEBRIDGE_APP_NAME,
        "data": event,
        # Required Version of Opt In Agreement
        "optInRequired": OPT_IN_VERSION,
    }


def post_request(uri, auth_header, logger, params=None, data=None, headers=None):
    """
    Makes a synchronous post request to a given uri
    :param uri: string representing uri to make request to
    :param params: Optional parameters to be append as the query string to the URL
    :param data: Request body
    :param auth_header: A value to supply for the Authorization header
    :param headers: header to send with post request.
    :return:
    """
    if not headers:
        headers = {HEADER_CONTENT_TYPE: APPLICATION_JSON}

    if auth_header is not None:
        headers[HEADER_AUTHORIZATION] = repr(auth_header)

    return requests.post(url=uri,
                         headers=headers,
                         params=params,
                         verify=False,
                         data=data)


def post_event(event_jsn, auth_header, logger):
    payload = create_telemetry_payload(event_jsn)
    r = post_request(uri=get_telemetry_uri(), auth_header=auth_header, logger=logger, data=json.dumps(payload))
    logger.debug("Posted metrics data to telemetry with response=%s" % str(r.text))
    return r


@defer.inlineCallbacks
def get_telemetry_instance_id(async_client, auth_header):
    rest_uri = rest.makeSplunkdUri()
    instance_id_uri = "{}services/properties/telemetry/general/deploymentID".format(rest_uri)
    r = yield async_client.async_get_request(instance_id_uri, auth_header=auth_header)
    if r.code != http.OK:
        error_text = yield r.text()
        LOGGER.info("Could not get telemetry instance id with error={} and status={}".format(error_text, r.code))
    instance_id = yield r.text()
    defer.returnValue(instance_id)


@defer.inlineCallbacks
def get_installation_environment(async_client, auth_header):
    rest_uri = rest.makeSplunkdUri()
    on_cloud_instance_uri = "{}services/properties/telemetry/general/onCloudInstance".format(rest_uri)
    r = yield async_client.async_get_request(on_cloud_instance_uri, auth_header=auth_header)
    if r.code != http.OK:
        error_text = yield r.text()
        LOGGER.info("Could not get telemetry instance id with error={} and status={}".format(error_text, r.code))
    installation_environment_response = yield r.text()
    installation_environment = InstallationEnvironment.CLOUD \
        if installation_environment_response.lower().strip() == "true" \
        else InstallationEnvironment.ENTERPRISE
    defer.returnValue(installation_environment)


@defer.inlineCallbacks
def get_splunk_version(async_client, auth_header):
    """
    Gets splunk version
    :param async_client:
    :param auth_header
    :return:
    """
    rest_uri = rest.makeSplunkdUri()
    server_info_uri = "{}/services/server/info".format(rest_uri)
    r = yield async_client.async_get_request(uri=server_info_uri, auth_header=auth_header,
                                             params={'output_mode': 'json'})
    if r.code != http.OK:
        error_text = yield r.text()
        LOGGER.info("Could not get splunk version with error={} and status={}".format(error_text, r.code))
    jsn = yield r.json()
    server_version = jsn['entry'][0]['content']['version']
    defer.returnValue(server_version)


class AsyncTelemetryClient(AsyncClient):
    """
    Client for making asynchronous requests to telemetry endpoint
    """

    telemetry_instance_id = None
    splunk_version = None
    installation_environment = None

    @defer.inlineCallbacks
    def get_telemetry_instance_id(self, auth_header):
        if self.telemetry_instance_id is None:
            yield self.set_telemetry_instance_id(auth_header)
        defer.returnValue(self.telemetry_instance_id)

    @defer.inlineCallbacks
    def set_telemetry_instance_id(self, auth_header):
        self.telemetry_instance_id = yield get_telemetry_instance_id(self, auth_header=auth_header)

    @defer.inlineCallbacks
    def get_splunk_version(self, auth_header):
        if self.splunk_version is None:
            yield self.set_splunk_version(auth_header)
        defer.returnValue(self.splunk_version)

    @defer.inlineCallbacks
    def set_splunk_version(self, auth_header):
        self.splunk_version = yield get_splunk_version(self, auth_header=auth_header)

    @defer.inlineCallbacks
    def get_installation_environment(self, auth_header):
        if self.installation_environment is None:
            yield self.set_installation_environment(auth_header)
        defer.returnValue(self.installation_environment)

    @defer.inlineCallbacks
    def set_installation_environment(self, auth_header):
        self.installation_environment = yield get_installation_environment(self, auth_header=auth_header)

    @defer.inlineCallbacks
    def post_metrics(self, event, auth_header, logger):
        uri = get_telemetry_uri()

        if self.telemetry_instance_id is None:
            yield self.set_telemetry_instance_id(auth_header)

        if self.splunk_version is None:
            yield self.set_splunk_version(auth_header)

        if self.installation_environment is None:
            yield self.set_installation_environment(auth_header)

        event.update({constants.INSTANCE_ID: self.telemetry_instance_id,
                      constants.SPLUNK_VERSION: self.splunk_version,
                      constants.INSTALLATION_ENVIRONMENT: self.installation_environment.name})
        payload = create_telemetry_payload(event)

        try:
            r = yield self.async_post_request(uri, auth_header=auth_header, data=json.dumps(payload))
            text = yield r.text()
        except Exception as e:
            logger.info(str(e))
