"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for accessing and setting AR workspace kvstore records
"""
import json
import os
import sys

os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from google.protobuf.json_format import Parse
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.messages.request_context import RequestContext
from spacebridgeapp.ar.websocket import ar_workspace_request_processor
from spacebridgeapp.rest import async_base_endpoint
from spacebridgeapp.rest.util.helper import extract_parameter
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, PAYLOAD, STATUS, QUERY
from splapp_protocol import augmented_reality_pb2
from twisted.internet import defer
from twisted.web import http


LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + ".log", "rest_ar_workspace_v2")


BODY_LABEL = 'body'
WORKSPACE_ID_LABEL = 'workspace_id'
INTEGRITY_HASH_LABEL = 'integrity_hash'
WORKSPACE_DATA_LABEL = 'workspace_data'
WORKSPACE_TITLE_LABEL = 'workspace_title'
TITLE_LABEL = 'title'
NEW_WORKSPACE_LABEL = 'is_new_workspace'
KVSTORE_DATA_LABEL = 'kvstore_data'


class ArWorkspaceV2(async_base_endpoint.AsyncBaseRestHandler):
    """Handles GET, PUT, POST, and DELETE HTTP requests pertaining to workspaces from the Splapp."""

    def __init__(self, *args, **kwargs):
        super(ArWorkspaceV2, self).__init__(*args, **kwargs)
        self.async_kvstore_client = self.async_client_factory.kvstore_client()
        self.async_ar_permissions_client = self.async_client_factory.ar_permissions_client()
        self.async_splunk_client = self.async_client_factory.splunk_client()

    @defer.inlineCallbacks
    def async_get(self, request):
        """Returns workspaces from KV store.

        If no workspace IDs are provided in the request, data for all workspaces is returned.
        """
        context = RequestContext.from_rest_request(request)
        workspace_ids = request[QUERY].get(WORKSPACE_ID_LABEL) or []
        if not isinstance(workspace_ids, list):
            workspace_ids = [workspace_ids]
        workspaces = yield ar_workspace_request_processor.get_ar_workspaces(context,
                                                                            self.async_kvstore_client,
                                                                            self.async_ar_permissions_client,
                                                                            workspace_ids,
                                                                            json_format=True)
        defer.returnValue({
            PAYLOAD: {'ar_workspaces': workspaces},
            STATUS: http.OK
        })

    @defer.inlineCallbacks
    def async_post(self, request):
        """Creates a new workspace.

        If no workspace ID is provided a randomly generated one will be used. The request must specify a workspace
        title.
        """
        response = yield self._create_or_update_workspace(request, create=True)
        defer.returnValue(response)

    @defer.inlineCallbacks
    def async_put(self, request):
        """Updates an existing workspace."""
        response = yield self._create_or_update_workspace(request, create=False)
        defer.returnValue(response)

    @defer.inlineCallbacks
    def _create_or_update_workspace(self, request, create):
        context = RequestContext.from_rest_request(request)
        payload = json.loads(request[PAYLOAD])

        workspace_proto = augmented_reality_pb2.ARWorkspaceData()
        if WORKSPACE_ID_LABEL in payload:
            workspace_proto.arWorkspaceId = payload[WORKSPACE_ID_LABEL]
        if WORKSPACE_TITLE_LABEL in payload:
            workspace_proto.title = payload[WORKSPACE_TITLE_LABEL]
        if KVSTORE_DATA_LABEL in payload:
            # We probably should update this API to accept an ARWorkspaceData in JSON format so we only have one way
            # to set things. I.e. if the ID or title is set in the following payload, it will overwrite the ID and title
            # set above.
            workspace_data = json.loads(payload[KVSTORE_DATA_LABEL]).get(WORKSPACE_DATA_LABEL, {})
            if isinstance(workspace_data, dict):
                workspace_data = json.dumps(workspace_data)
            workspace_proto = Parse(workspace_data, workspace_proto)

        if create:
            affected_workspace_id = yield ar_workspace_request_processor.create_ar_workspace(
                context,
                self.async_splunk_client,
                self.async_kvstore_client,
                self.async_ar_permissions_client,
                workspace_proto)
        else:
            affected_workspace_id = yield ar_workspace_request_processor.update_ar_workspace(
                context,
                self.async_client_factory.kvstore_client(),
                self.async_client_factory.ar_permissions_client(),
                workspace_proto)

        defer.returnValue({
            PAYLOAD: {WORKSPACE_ID_LABEL: affected_workspace_id},
            STATUS: http.OK
        })

    @defer.inlineCallbacks
    def async_delete(self, request):
        """Deletes a workspace by ID."""
        context = RequestContext.from_rest_request(request)
        workspace_id = extract_parameter(request[QUERY], WORKSPACE_ID_LABEL, QUERY)
        deleted_ids = yield ar_workspace_request_processor.delete_ar_workspace(
            context, self.async_client_factory.kvstore_client(), self.async_client_factory.ar_permissions_client(),
            [workspace_id])
        defer.returnValue({
            PAYLOAD: {WORKSPACE_ID_LABEL: deleted_ids},
            STATUS: http.OK,
        })
