"""
(C) 2020 Splunk Inc. All rights reserved.

REST handler for applying visualization changes to workspaces.
"""
import json
import sys

from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from google.protobuf.json_format import Parse, ParseError, MessageToDict
from spacebridgeapp.ar.visualizations.workspace_layout import set_default_layout
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.rest import async_base_endpoint
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, PAYLOAD, STATUS
from splapp_protocol.augmented_reality_pb2 import ARWorkspaceData
from twisted.web import http


LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + ".log", "visualizations")


class Visualizations(async_base_endpoint.AsyncBaseRestHandler):

    def async_post(self, request):
        workspace = request.get(PAYLOAD)
        if not workspace:
            return {
                PAYLOAD: {'reason': 'Request payload must include JSON formatted ARWorkspaceData.'},
                STATUS: http.BAD_REQUEST,
            }

        try:
            workspace = Parse(workspace, ARWorkspaceData())
            workspace = set_default_layout(workspace)
            return {
                PAYLOAD: {'workspace': MessageToDict(workspace, including_default_value_fields=True)},
                STATUS: http.OK
            }
        except ParseError as e:
            return {
                PAYLOAD: {
                    'reason': 'Failed to parse workspace payload.',
                    'exception': str(e),
                },
                STATUS: http.BAD_REQUEST
            }
