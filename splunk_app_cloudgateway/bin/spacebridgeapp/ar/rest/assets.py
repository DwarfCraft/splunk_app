"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for accessing and setting asset kvstore records
"""

import sys
import json

from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from spacebridgeapp.ar.data.asset_data import AssetData
from spacebridgeapp.ar.data.asset_group_data import AssetGroup
from spacebridgeapp.ar.permissions.async_permissions_client import ARObjectType, Capabilities
from spacebridgeapp.ar.rest.common import validate_asset_or_group_objects
from spacebridgeapp.ar.storage.assets import get_assets, delete_assets
from spacebridgeapp.ar.storage.asset_groups import create_asset_group, AssetGroupAlreadyExists
from spacebridgeapp.ar.websocket.ar_workspace_request_processor import (
    WORKSPACE_MANAGE_PERMISSION_REQUIRED, create_ar_workspace
)
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeARPermissionError, SpacebridgeApiRequestError
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.messages.request_context import RequestContext
from spacebridgeapp.rest import async_base_endpoint
from spacebridgeapp.util.constants import (
    SPACEBRIDGE_APP_NAME, ASSET_OBJECTS, NEW_WORKSPACE_TITLE, ASSET_GROUP_ID, ASSETS, ASSET_GROUP_NAME, ASSET_IDS,
    QUERY, PAYLOAD, ACTION, CREATE, UPDATE, DELETE, STATUS, ASSET_ID, ASSET_NAME, ASSET_TYPE, AR_WORKSPACE_ID_KEY,
    DASHBOARD_ID_KEY, ASSETS_COLLECTION_NAME
)
from splapp_protocol.augmented_reality_pb2 import ARWorkspaceData
from splapp_protocol.common_pb2 import DashboardDescription
from twisted.internet import defer
from twisted.web import http

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + ".log", "rest_assets")


class Assets(async_base_endpoint.AsyncBaseRestHandler):
    """REST handler for viewing and managing AR assets."""

    def __init__(self, *args, **kwargs):
        super(Assets, self).__init__(*args, **kwargs)
        self._permissions = self.async_client_factory.ar_permissions_client()
        self._kvstore = self.async_client_factory.kvstore_client()
        self._splunk = self.async_client_factory.splunk_client()

    @defer.inlineCallbacks
    def async_get(self, request):
        """Looks up assets from KV store."""
        context = RequestContext.from_rest_request(request)
        asset_ids = request[QUERY].get(ASSET_IDS)
        assets = yield get_assets(context, asset_ids, self._kvstore, self._permissions, ungroup_assets=False)
        defer.returnValue({
            PAYLOAD: {ASSETS: [asset.to_dict() for asset in assets]},
            STATUS: http.OK
        })

    @defer.inlineCallbacks
    def async_post(self, request):
        """Handles creating and modifying assets.

        The payload parameters used by this handler include:
            - action: determines what to do with the given assets. Either update, create, or delete.
            - assets: a list of JSON document assets to update or create.
            - asset_objects: a list of objects to associate with the given asset or asset group.
            - asset_group_id: the ID of an existing asset group to associate with the above assets.
            - asset_group_name: the name of a new asset group to create and associate with the above assets.
            - new_workspace_title: the name of a new workspace to create and associate with the given assets or asset
                                   group.
            - overwrite: bool indicating whether to overwrite existing asset data.
        """
        context = RequestContext.from_rest_request(request)
        params = json.loads(request[PAYLOAD])
        if ACTION not in params or params[ACTION] not in {CREATE, UPDATE, DELETE}:
            raise SpacebridgeApiRequestError(message='Must provide an action', status_code=http.BAD_REQUEST)

        if params.get(ACTION) == DELETE:
            deleted_ids = yield delete_assets(context, params.get(ASSET_IDS), self._kvstore, self._permissions)
            defer.returnValue({
                PAYLOAD: {ASSET_IDS: deleted_ids},
                STATUS: http.OK
            })

        yield self._check_user_can_do_update(context, params)

        # Create a workspace if the user specifies a new workspace title
        dashboard_id, workspace_id = _get_asset_object_ids(params)
        if params.get(NEW_WORKSPACE_TITLE):
            workspace_id = yield create_ar_workspace(context, self._splunk, self._kvstore, self._permissions,
                                                     ARWorkspaceData(title=params.get(NEW_WORKSPACE_TITLE)),
                                                     dashboard_id=dashboard_id)
            LOGGER.debug('Created workspace_id=%s', workspace_id)

        # Create an asset group if the user specifies a new group name
        asset_group_id = params.get(ASSET_GROUP_ID)
        if params.get(ASSET_GROUP_NAME):
            asset_group = AssetGroup(
                name=params.get(ASSET_GROUP_NAME),
                key=asset_group_id,
                dashboard_id=dashboard_id,
                workspace_id=workspace_id
            )
            try:
                asset_group_id = yield create_asset_group(context, asset_group, self._kvstore, self._permissions)
            except AssetGroupAlreadyExists as e:
                LOGGER.debug(e)

        assets = [AssetData(
            asset_name=asset.get(ASSET_NAME),
            asset_id=asset.get(ASSET_ID),
            asset_group=asset_group_id,
            is_splunk_generated=asset.get(ASSET_TYPE) or ASSET_ID in asset,
            dashboard_description_pb=DashboardDescription(dashboardId=dashboard_id),
            ar_workspace_data_pb=ARWorkspaceData(arWorkspaceId=workspace_id)
        ) for asset in params.get(ASSETS, [])]
        affected_ids = yield self._kvstore.async_batch_save_request(
            auth_header=context.auth_header, collection=ASSETS_COLLECTION_NAME,
            entries=[asset.to_dict(jsonify_objects=True) for asset in assets])
        if not asset_group_id:
            yield self._permissions.register_objects(context, ARObjectType.ASSET, affected_ids,
                                                     check_if_objects_exist=True)

        # Return the IDs that were affected by this request
        defer.returnValue({
            PAYLOAD: {
                'asset_ids': affected_ids or [],
                'workspace_id': workspace_id,
                'asset_group_id': asset_group_id,
            },
            STATUS: http.OK if params[ACTION] == UPDATE else http.CREATED
        })

    @defer.inlineCallbacks
    def _check_user_can_do_update(self, context, params):
        """
        Checks that the user has permission to execute asset POST request with the given parameters.

        This is important to do ahead of time since we need the request to be atomic. For example, if the user is able
        to create workspaces but not assets, we don't want workspace creation to succeed and asset creation to fail.
        """
        validate_asset_or_group_objects(params.get(ASSET_OBJECTS), new_workspace_title=params.get(NEW_WORKSPACE_TITLE),
                                        asset_is_grouped=ASSET_GROUP_ID in params)
        (can_manage_workspaces, can_manage_groups,
         can_manage_assets) = yield self._permissions.check_multiple_permissions(
            context, [Capabilities.WORKSPACE_MANAGE, Capabilities.ASSET_GROUP_MANAGE, Capabilities.ASSET_MANAGE],
            raise_on_missing=False)

        # The user can do whatever they want so there's no point in the checks to follow
        if can_manage_workspaces and can_manage_groups and can_manage_assets:
            defer.returnValue(True)

        # The user needs to be able to create workspaces
        if params.get(NEW_WORKSPACE_TITLE) and not can_manage_workspaces:
            raise SpacebridgeARPermissionError(WORKSPACE_MANAGE_PERMISSION_REQUIRED)

        # The user needs to be able to create asset groups
        if params.get(ASSET_GROUP_NAME) and not can_manage_groups:
            raise SpacebridgeARPermissionError('Cannot create asset groups without asset_group_manage')

        # The user need to update either grouped or ungrouped assets
        yield self._check_user_can_update_assets(context, params, can_manage_assets, can_manage_groups)

    @defer.inlineCallbacks
    def _check_user_can_update_assets(self, context, params, can_manage_assets, can_manage_groups):
        assets = params.get(ASSETS, [])
        asset_ids = [asset[ASSET_ID] for asset in assets if ASSET_ID in asset]

        existing_assets = []
        if asset_ids:
            existing_assets = yield get_assets(context, asset_ids, self._kvstore, self._permissions,
                                               ungroup_assets=False, ignore_permissions=True)
        if not can_manage_assets and len(assets) > len(existing_assets):
            raise SpacebridgeARPermissionError('Cannot create new assets without asset_manage')
        updated_assets_by_id = {asset[ASSET_ID]: asset for asset in assets if ASSET_ID in asset}

        asset_access, group_access = yield self._permissions.get_accessible_objects(
            context, Capabilities.ASSET_WRITE, Capabilities.ASSET_GROUP_WRITE)
        dashboard_id, workspace_id = _get_asset_object_ids(params)
        for existing_asset in existing_assets:
            updated_asset = updated_assets_by_id[existing_asset.asset_id]
            if not can_manage_groups and existing_asset.asset_group != params.get(ASSET_GROUP_ID):
                raise SpacebridgeARPermissionError('Must have asset_group_manage to move assets between groups.')

            assets_differ = (
                existing_asset.asset_name != updated_asset[ASSET_NAME] or
                existing_asset.asset_type != updated_asset[ASSET_TYPE] or
                existing_asset.dashboard_id != dashboard_id or
                existing_asset.workspace_id != workspace_id
            )
            if assets_differ:
                user_can_edit_asset = (
                    can_manage_groups or existing_asset.asset_group in group_access.ids
                    if existing_asset.asset_group else
                    can_manage_assets or existing_asset.asset_id in asset_access.ids
                )
                if not user_can_edit_asset:
                    raise SpacebridgeARPermissionError(
                        'Must have asset_write or asset_group_write on asset or group id={}'.format(
                            existing_asset.asset_id))


def _get_asset_object_ids(params):
    asset_object = {}
    if ASSET_OBJECTS in params and params[ASSET_OBJECTS]:
        asset_object = params[ASSET_OBJECTS][0]
    return asset_object.get(DASHBOARD_ID_KEY), asset_object.get(AR_WORKSPACE_ID_KEY)
