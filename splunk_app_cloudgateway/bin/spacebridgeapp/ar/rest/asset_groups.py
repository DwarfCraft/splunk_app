"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for accessing and setting asset kvstore records
"""

import sys
import json

from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from spacebridgeapp.ar.data.asset_group_data import AssetGroup
from spacebridgeapp.ar.rest.common import validate_asset_or_group_objects
from spacebridgeapp.ar.storage.asset_groups import get_asset_groups, delete_asset_groups, bulk_update_asset_groups
from spacebridgeapp.ar.websocket.ar_workspace_request_processor import create_ar_workspace
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.messages.request_context import RequestContext
from spacebridgeapp.rest import async_base_endpoint
from spacebridgeapp.util.constants import (
    SPACEBRIDGE_APP_NAME, ASSET_GROUP_IDS, QUERY, PAYLOAD, ASSET_GROUPS, ACTION, CREATE, UPDATE, DELETE, STATUS,
    ASSET_GROUP_ID, KEY, ASSET_GROUP_OBJECTS, NEW_WORKSPACE_TITLE
)
from splapp_protocol.augmented_reality_pb2 import ARWorkspaceData
from twisted.internet import defer
from twisted.web import http


LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_asset_groups", "asset_groups_rest")
ASSET_GROUP_IDS_RESPONSE_KEY = 'ids'


class AssetGroups(async_base_endpoint.AsyncBaseRestHandler):
    """REST handler for asset group related operations."""

    def __init__(self, *args, **kwargs):
        super(AssetGroups, self).__init__(*args, **kwargs)
        self._permissions = self.async_client_factory.ar_permissions_client()
        self._kvstore = self.async_client_factory.kvstore_client()
        self._splunk = self.async_client_factory.splunk_client()

    @defer.inlineCallbacks
    def async_get(self, request):
        """Returns a list of asset groups. If no asset group IDs are specified, all will be returned."""
        context = RequestContext.from_rest_request(request)
        asset_group_ids = request[QUERY].get(ASSET_GROUP_IDS)
        asset_groups = yield get_asset_groups(context, asset_group_ids, self._kvstore, self._permissions)
        defer.returnValue({
            PAYLOAD: {ASSET_GROUPS: [asset_group.to_dict() for asset_group in asset_groups]},
            STATUS: http.OK
        })

    @defer.inlineCallbacks
    def async_post(self, request):
        """Handles updates to asset groups."""
        context = RequestContext.from_rest_request(request)
        params = json.loads(request[PAYLOAD])
        if ACTION not in params or params[ACTION] not in {CREATE, UPDATE, DELETE}:
            raise SpacebridgeApiRequestError(message='Must provide an action', status_code=http.BAD_REQUEST)

        if params[ACTION] == DELETE:
            asset_group_ids = params[ASSET_GROUP_IDS]
            deleted_ids = yield delete_asset_groups(context, asset_group_ids, self._kvstore, self._permissions)
            defer.returnValue({
                PAYLOAD: {ASSET_GROUP_IDS: deleted_ids},
                STATUS: http.OK
            })

        if ASSET_GROUPS not in params:
            raise SpacebridgeApiRequestError('Must provide asset groups to update', status_code=http.BAD_REQUEST)
        asset_groups = params[ASSET_GROUPS]
        for asset_group in asset_groups:
            validate_asset_or_group_objects(asset_group.get(ASSET_GROUP_OBJECTS), new_workspace_title=None)
            if ASSET_GROUP_ID in asset_group:
                asset_group[KEY] = asset_group[ASSET_GROUP_ID]

        asset_group_data = []
        for asset_group in asset_groups:
            parsed_group = AssetGroup.from_json(asset_group)
            if NEW_WORKSPACE_TITLE in asset_group:
                # Today the only time NEW_WORKSPACE_TITLE will be specified is when there is only one asset group being
                # updated so it's safe to assume that this will not spawn many KV store requests.
                created_workspace_id = yield create_ar_workspace(
                    context, self._splunk, self._kvstore, self._permissions,
                    ARWorkspaceData(title=asset_group[NEW_WORKSPACE_TITLE]), dashboard_id=parsed_group.dashboard_id)
                parsed_group.workspace_id = created_workspace_id
            asset_group_data.append(parsed_group)

        affected_groups = yield bulk_update_asset_groups(context, asset_group_data, self._kvstore, self._permissions)
        defer.returnValue({
            PAYLOAD: {ASSET_GROUP_IDS_RESPONSE_KEY: affected_groups},
            STATUS: http.OK if params[ACTION] == UPDATE else http.CREATED
        })
