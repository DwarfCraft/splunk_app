"""
Module to process Location Related Requests
"""
from spacebridgeapp.ar.data.asset_data import AssetData
from spacebridgeapp.ar.storage.assets import (
    get_assets, delete_assets, create_asset, update_asset, AssetAlreadyExistsException
)
from spacebridgeapp.ar.websocket.ar_workspace_request_processor import get_ar_workspaces
from spacebridgeapp.dashboard.dashboard_helpers import to_dashboard_key
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError, SpacebridgeARPermissionError
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.request.dashboard_request_processor import fetch_dashboard_descriptions
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, VIEW_PERMISSION_REQUIRED, MODIFY_PERMISSION_REQUIRED
from splapp_protocol.augmented_reality_pb2 import ARWorkspaceData
from splapp_protocol.common_pb2 import DashboardDescription
from twisted.internet import defer
from twisted.web import http


LOGGER = setup_logging('{}_asset_request_processor'.format(SPACEBRIDGE_APP_NAME), "asset_request_processor")


ASSET_VIEW_PERMISSION_REQUIRED = VIEW_PERMISSION_REQUIRED.format(object_type='asset')
ASSET_MODIFY_PERMISSION_REQUIRED = MODIFY_PERMISSION_REQUIRED.format(object_type='asset')


@defer.inlineCallbacks
def process_asset_get_request(request_context,
                              client_single_request,
                              server_single_response,
                              async_splunk_client,
                              async_kvstore_client,
                              async_ar_permissions_client):
    """
    Returns a list of AssetData messages for each of the given asset IDs in the request.

    :param request_context: a request_context.RequestContext
    :param client_single_request: reference client request object
    :param server_single_response: pass-by-reference return object
    :param async_splunk_client: an async_splunk_client.AsyncSplunkClient
    :param async_kvstore_client: an async_kvstore_client.AsyncKvStoreClient
    :param async_ar_permissions_client: an async_ar_permissions_client.AsyncArPermissionsClient
    """
    asset_ids = client_single_request.assetGetRequest.assetIds
    assets = yield get_assets(asset_ids=asset_ids, request_context=request_context, kvstore_client=async_kvstore_client,
                              permission_client=async_ar_permissions_client)
    if not assets:
        LOGGER.info('No asset associated with asset_id=%s', asset_ids)
        server_single_response.assetGetResponse.SetInParent()
        defer.returnValue(True)

    dashboard_ids, workspace_ids = ({asset.dashboard_id for asset in assets if asset.dashboard_id},
                                    {asset.workspace_id for asset in assets if asset.workspace_id})
    LOGGER.debug('type=ASSET_GET_REQUEST querying dashboard_ids=%s workspace_ids=%s', dashboard_ids, workspace_ids)
    dashboards_by_id = yield _get_dashboards_by_id(dashboard_ids, request_context, async_splunk_client)
    workspaces_by_id = yield _get_workspace_by_id(workspace_ids, request_context, async_kvstore_client,
                                                  async_ar_permissions_client)
    for asset in assets:
        dashboard = dashboards_by_id.get(to_dashboard_key(asset.dashboard_id))
        if not dashboard:
            raise SpacebridgeApiRequestError('No dashboard data for dashboard_id={}'.format(asset.dashboard_id),
                                             status_code=http.INTERNAL_SERVER_ERROR)

        workspace = workspaces_by_id.get(asset.workspace_id)
        if not workspace and asset.workspace_id:
            raise SpacebridgeApiRequestError('No workspace data for workspace_id={}'.format(asset.workspace_id),
                                             status_code=http.INTERNAL_SERVER_ERROR)

        asset.dashboard.MergeFrom(dashboard)
        if workspace:
            asset.workspace.MergeFrom(workspace)

    del server_single_response.assetGetResponse.assets[:]
    server_single_response.assetGetResponse.assets.extend([asset.to_protobuf() for asset in assets])


@defer.inlineCallbacks
def process_asset_set_request(request_context,
                              client_single_request,
                              server_single_response,
                              async_kvstore_client,
                              async_ar_permissions_client):
    """
    This method processes asset set requests

    :param request_context: a request_context.RequestContext
    :param client_single_request: reference client request object
    :param server_single_response: pass-by-reference return object
    :param async_kvstore_client: an async_kvstore_client.AsyncKvStoreClient
    :param async_ar_permissions_client: an async_ar_permissions_client.AsyncArPermissionsClient
    """
    params = client_single_request.assetSetRequest.params
    if not params:
        raise SpacebridgeApiRequestError("Call to AR ASSET SET failed. No params passed in.",
                                         status_code=http.BAD_REQUEST)

    # In the past this API supported multi-asset updates and creates. The AR app never updates or creates more than one
    # asset at a time (nor did it ever) so to simplify things on this side we only support updating one asset at a time
    # despite the request protocol allowing for multi-asset updates.
    if len(params) > 1:
        raise SpacebridgeApiRequestError('Can only specify a single asset to create or update.',
                                         status_code=http.BAD_REQUEST)
    param = params[0]
    if not param.assetName:
        raise SpacebridgeApiRequestError('All assets must have a name', status_code=http.BAD_REQUEST)
    if not param.objects or len(param.objects) > 1:
        raise SpacebridgeApiRequestError('Must specify exactly one asset object per update.',
                                         status_code=http.BAD_REQUEST)
    asset_object = param.objects[0]

    dashboard = None
    if asset_object.HasField('dashboardId'):
        dashboard = DashboardDescription(dashboardId=asset_object.dashboardId)

    workspace = None
    if asset_object.HasField('arWorkspaceSetAsset'):
        dashboard = DashboardDescription(dashboardId=asset_object.arWorkspaceSetAsset.dashboardId)
        workspace = ARWorkspaceData(arWorkspaceId=asset_object.arWorkspaceSetAsset.arWorkspaceId)

    asset = AssetData(
        asset_id=param.assetId,
        asset_name=param.assetName,
        dashboard_description_pb=dashboard,
        ar_workspace_data_pb=workspace
    )

    try:
        created_id = yield create_asset(request_context, asset, async_kvstore_client, async_ar_permissions_client)
        LOGGER.debug('Registered asset_id=%s', created_id)
        server_single_response.assetSetResponse.SetInParent()
    except (AssetAlreadyExistsException, SpacebridgeARPermissionError):
        updated_id = yield update_asset(request_context, asset, async_kvstore_client, async_ar_permissions_client)
        LOGGER.debug('Updated asset_id=%s', updated_id)
        server_single_response.assetSetResponse.SetInParent()


@defer.inlineCallbacks
def process_asset_delete_request(request_context,
                                 client_single_request,
                                 server_single_response,
                                 async_kvstore_client,
                                 async_ar_permissions_client):
    """
    This method processes asset delete requests

    :param request_context: a request_context.RequestContext
    :param client_single_request: reference client request object
    :param server_single_response: pass-by-reference return object
    :param async_kvstore_client: an async_kvstore_client.AsyncKvStoreClient
    :param async_ar_permissions_client: an async_ar_permissions_client.AsyncArPermissionsClient
    """
    asset_ids = client_single_request.assetDeleteRequest.assetIds
    yield delete_assets(request_context, asset_ids, async_kvstore_client, async_ar_permissions_client)
    server_single_response.assetDeleteResponse.SetInParent()


@defer.inlineCallbacks
def _get_workspace_by_id(workspace_ids, request_context, async_kvstore_client, async_ar_permissions_client):
    workspaces = yield get_ar_workspaces(request_context, async_kvstore_client, async_ar_permissions_client,
                                         workspace_ids)
    defer.returnValue({workspace.arWorkspaceId: workspace for workspace in workspaces})


@defer.inlineCallbacks
def _get_dashboards_by_id(dashboard_ids,
                          request_context,
                          async_splunk_client):
    dashboard_list, _ = yield fetch_dashboard_descriptions(request_context=request_context,
                                                           dashboard_ids=dashboard_ids,
                                                           async_splunk_client=async_splunk_client)
    dashboard_dict = {to_dashboard_key(description.dashboard_id): description.to_protobuf()
                      for description in dashboard_list}
    defer.returnValue(dashboard_dict)
