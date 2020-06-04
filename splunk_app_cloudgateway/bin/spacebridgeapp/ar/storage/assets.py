"""
(C) 2020 Splunk Inc. All rights reserved.

Provides access to the AR assets KV store collection.
"""
import json

from spacebridgeapp.ar.ar_util import is_non_string_iterable
from spacebridgeapp.ar.data.asset_data import AssetData
from spacebridgeapp.ar.permissions.async_permissions_client import Capabilities, AccessQuantity, ARObjectType
from spacebridgeapp.ar.storage.queries import get_query_matching_keys
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError, SpacebridgeARPermissionError
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.constants import (
    KEY, ASSETS_COLLECTION_NAME, SPACEBRIDGE_APP_NAME, ASSET_OBJECTS, ASSET_GROUP, AND_OPERATOR, OR_OPERATOR,
    ASSET_GROUP_OBJECTS, ASSET_GROUPS_COLLECTION_NAME, QUERY,
    MANAGE_PERMISSION_REQUIRED
)
from twisted.internet import defer
from twisted.web import http

LOGGER = setup_logging('{}_assets.log'.format(SPACEBRIDGE_APP_NAME), "assets")
ASSET_MANAGE_PERMISSION_REQUIRED = MANAGE_PERMISSION_REQUIRED.format(object_type='asset')


class MissingAssetIDException(SpacebridgeApiRequestError):
    def __init__(self, message):
        super(MissingAssetIDException, self).__init__(message, status_code=http.BAD_REQUEST)


class NoSuchAssetException(SpacebridgeApiRequestError):
    def __init__(self, asset_id):
        super(NoSuchAssetException, self).__init__(message='asset_id={} does not exist'.format(asset_id),
                                                   status_code=http.NOT_FOUND)


class AssetAlreadyExistsException(SpacebridgeApiRequestError):
    def __init__(self, asset_id):
        super(AssetAlreadyExistsException, self).__init__(message='asset_id={} already exists'.format(asset_id),
                                                          status_code=http.CONFLICT)


@defer.inlineCallbacks
def get_assets(request_context, asset_ids, kvstore_client, permission_client, ungroup_assets=True,
               ignore_permissions=False):
    """
    Retrieves the given assets from KV store.

    :param request_context: the RequestContext of the caller
    :param asset_ids: the asset IDs to query
    :param kvstore_client: the AsyncKvStoreClient to query KV store with
    :param permission_client: the AsyncArPermissionsClient to validate permissions with
    :param ungroup_assets: whether to unpack grouped asset data into each individual asset
    :param ignore_permissions: if True, permissions will not be checked. This should only be True when permissions are
                               validated in advance OR the resulting assets will not be returned to the user.
    :return: a list of AssetData (not the protobuf) for each asset retrieved
    """
    if asset_ids and not is_non_string_iterable(asset_ids):
        asset_ids = [asset_ids]

    if ignore_permissions:
        should_query, assets_query = True, {QUERY: get_query_matching_keys(asset_ids)}
    else:
        asset_access, asset_group_access = yield permission_client.get_accessible_objects(
            request_context, Capabilities.ASSET_READ, Capabilities.ASSET_GROUP_READ)
        should_query, assets_query = _build_get_assets_query(asset_ids, asset_access, asset_group_access)
    if not should_query:
        defer.returnValue([])

    assets_kvstore_response = yield kvstore_client.async_kvstore_get_request(
        collection=ASSETS_COLLECTION_NAME, auth_header=request_context.auth_header, params=assets_query)
    if assets_kvstore_response.code != http.OK:
        message = yield assets_kvstore_response.text()
        raise SpacebridgeApiRequestError("Failed to lookup assets with query={} status_code={} message={}".format(
            assets_query, assets_kvstore_response.code, message), status_code=assets_kvstore_response.code)

    assets = yield assets_kvstore_response.json()
    if ungroup_assets:
        asset_group_ids, grouped_assets, ungrouped_assets = _extract_asset_group_ids_from_assets(assets)
        ungrouped_assets += yield _ungroup_assets_with_group_ids(grouped_assets, asset_group_ids, request_context,
                                                                 kvstore_client)
        assets = ungrouped_assets

    defer.returnValue([AssetData.from_json(asset) for asset in assets])


def _build_get_assets_query(asset_ids, asset_access, asset_group_access):
    # The user can read everything and since they didn't specify which assets they want we should retrieve everything
    if not asset_ids and asset_access.quantity == asset_group_access.quantity == AccessQuantity.ALL:
        return True, None

    # The user can read all asset groups so we shouldn't consider them when building the query. Just search based on
    # asset ID.
    if asset_group_access.quantity == AccessQuantity.ALL:
        if asset_access.quantity == AccessQuantity.SOME:
            asset_ids = ({asset_id for asset_id in asset_ids if asset_id in asset_access.ids}
                         if asset_ids else asset_access.ids)
            if not asset_ids:
                return False, None
        return True, {QUERY: get_query_matching_keys(asset_ids)}

    # Query for assets that are not in a group and have one of the given asset IDs
    individual_assets_query = None
    assets_to_consider = set(asset_ids) if asset_ids else set()
    if asset_access.quantity == AccessQuantity.NONE:
        assets_to_consider.clear()
    if asset_access.quantity == AccessQuantity.SOME:
        assets_to_consider = asset_access.ids if not assets_to_consider else assets_to_consider & asset_access.ids

    group_filter = {ASSET_GROUP: None}
    if assets_to_consider:
        individual_assets_query = {
            AND_OPERATOR: [
                group_filter,
                {OR_OPERATOR: [{KEY: asset_id} for asset_id in assets_to_consider]}
            ]
        }
    elif asset_access.quantity == AccessQuantity.ALL:
        individual_assets_query = group_filter

    # Query for assets that are in a group and have one of the given asset IDs
    grouped_asset_query = None
    if asset_group_access.quantity == AccessQuantity.SOME:
        grouped_asset_query = {OR_OPERATOR: [{ASSET_GROUP: group_id} for group_id in asset_group_access.ids]}

    if asset_ids and grouped_asset_query:
        grouped_asset_query = {
            AND_OPERATOR: [
                grouped_asset_query,
                {OR_OPERATOR: [{KEY: asset_id} for asset_id in asset_ids]}
            ]
        }

    queries = [query for query in (individual_assets_query, grouped_asset_query) if query]

    # The user does not have access to anything so the query should not be executed.
    if not queries:
        return False, None

    if len(queries) == 1:
        return True, {QUERY: json.dumps(queries[0])}
    return True, {QUERY: json.dumps({OR_OPERATOR: queries})}


def _extract_asset_group_ids_from_assets(assets):
    asset_group_ids = set()
    grouped_assets = []
    ungrouped_assets = []
    for asset in assets:
        if ASSET_GROUP in asset:
            asset_group_ids.add(asset[ASSET_GROUP])
            grouped_assets.append(asset)
        else:
            ungrouped_assets.append(asset)
    return asset_group_ids, grouped_assets, ungrouped_assets


@defer.inlineCallbacks
def _ungroup_assets_with_group_ids(grouped_assets, asset_group_ids, request_context, kvstore_client):
    params = None
    if asset_group_ids:
        params = {QUERY: get_query_matching_keys(asset_group_ids)}
    LOGGER.debug('Looking up asset groups with query=%s', params)
    asset_groups_response = yield kvstore_client.async_kvstore_get_request(collection=ASSET_GROUPS_COLLECTION_NAME,
                                                                           auth_header=request_context.auth_header,
                                                                           params=params)
    if asset_groups_response.code != http.OK:
        message = yield asset_groups_response.text()
        raise SpacebridgeApiRequestError('Failed to lookup asset groups message={} status_code={}'.format(
            message, asset_groups_response.code), status_code=asset_groups_response.code)

    asset_groups = yield asset_groups_response.json()
    asset_groups_dict = {asset_group[KEY]: asset_group for asset_group in asset_groups}
    for asset in grouped_assets:
        asset[ASSET_OBJECTS] = asset_groups_dict[asset[ASSET_GROUP]][ASSET_GROUP_OBJECTS]
        del asset[ASSET_GROUP]
    defer.returnValue(grouped_assets)


@defer.inlineCallbacks
def update_asset(request_context, asset_data, kvstore, permissions):
    """
    Updates a single already existing asset.

    :param request_context: the RequestContext of the caller
    :param asset_data: the asset to update
    :param kvstore: the AsyncKvStoreClient to query KV store with
    :param permissions: the AsyncArPermissionsClient to validate permissions with
    :return: the ID of the updated asset
    """
    if not asset_data.asset_id:
        raise MissingAssetIDException('Must provide an asset ID when updating an asset.')

    existing_asset_response = yield kvstore.async_kvstore_get_request(collection=ASSETS_COLLECTION_NAME,
                                                                      auth_header=request_context.auth_header,
                                                                      key_id=asset_data.asset_id)
    if existing_asset_response.code != http.OK:
        message = yield existing_asset_response.text()
        raise SpacebridgeApiRequestError('Failed to load asset_id={} message={} status_code={}'.format(
            asset_data.asset_id, message, existing_asset_response.code),
            status_code=existing_asset_response.code)
    existing_asset = yield existing_asset_response.json()
    existing_asset = AssetData.from_json(existing_asset)

    # The asset group changed. Users must have asset_group_manage to do this.
    if asset_data.asset_group != existing_asset.asset_group:
        message = 'User username={} needs asset_group_manage to update the asset group for asset_id={}'.format(
            request_context.current_user, asset_data.asset_id)
        yield permissions.check_permission(request_context, Capabilities.ASSET_GROUP_MANAGE, message=message)

    if asset_data.asset_group:
        yield permissions.check_object_permission(
            request_context, Capabilities.ASSET_GROUP_WRITE, asset_data.asset_group, )
    else:
        yield permissions.check_object_permission(request_context, Capabilities.ASSET_WRITE, asset_data.asset_id)

    update_response = yield kvstore.async_kvstore_post_request(collection=ASSETS_COLLECTION_NAME,
                                                               auth_header=request_context.auth_header,
                                                               key_id=asset_data.asset_id,
                                                               data=asset_data.to_json())
    if update_response.code == http.NOT_FOUND:
        raise NoSuchAssetException(asset_id=asset_data.asset_id)
    if update_response.code != http.OK:
        message = yield update_response.text()
        raise SpacebridgeApiRequestError(
            'Failed to update asset_id={} with payload={} message={} status_code={}'.format(
                asset_data.asset_id, asset_data.to_json(), message, update_response.code),
            status_code=update_response.code)

    defer.returnValue(asset_data.asset_id)


@defer.inlineCallbacks
def create_asset(request_context, asset_data, kvstore, permissions):
    """
    Creates a new asset. If an ID is present it will be used but otherwise a new one will be generated.

    :param request_context: the RequestContext of the caller
    :param asset_data: the asset to create
    :param kvstore: the AsyncKvStoreClient to query KV store with
    :param permissions: the AsyncArPermissionsClient to validate permissions with
    :return: the ID of the created asset
    """
    can_manage_assets, can_manage_asset_groups = yield permissions.check_multiple_permissions(
        request_context, [Capabilities.ASSET_MANAGE, Capabilities.ASSET_GROUP_MANAGE], raise_on_missing=False)

    if not can_manage_assets:
        raise SpacebridgeARPermissionError('User username={} must have asset_manage to create new assets.'.format(
            request_context.current_user))

    if asset_data.asset_group and not can_manage_asset_groups:
        raise SpacebridgeARPermissionError(
            'User username={} must have asset_group_manage to create grouped assets'.format(
                request_context.current_user))

    create_asset_response = yield kvstore.async_kvstore_post_request(
        collection=ASSETS_COLLECTION_NAME, auth_header=request_context.auth_header, data=asset_data.to_json())
    if create_asset_response.code == http.CONFLICT:
        raise AssetAlreadyExistsException(asset_data.asset_id)
    if create_asset_response.code not in {http.OK, http.CREATED}:
        message = yield create_asset_response.text()
        raise SpacebridgeApiRequestError('Unable to create new asset message={} status_code={}'.format(
            message, create_asset_response.code), status_code=create_asset_response.code)
    created_asset_json = yield create_asset_response.json()
    created_asset_id = created_asset_json[KEY]
    yield permissions.register_objects(request_context, ARObjectType.ASSET, [created_asset_id])
    defer.returnValue(created_asset_id)


@defer.inlineCallbacks
def delete_assets(request_context, asset_ids, kvstore, permissions):
    """
    Deletes one or more assets.

    :param request_context: the RequestContext of the caller
    :param asset_ids: the assets to delete
    :param kvstore: the AsyncKvStoreClient to query KV store with
    :param permissions: the AsyncArPermissionsClient to validate permissions with
    :return: a list of the deleted asset IDs.
    """
    if not asset_ids:
        raise ValueError('Must specify asset_ids when deleting assets')
    if asset_ids and not is_non_string_iterable(asset_ids):
        asset_ids = [asset_ids]
    yield permissions.check_permission(request_context, Capabilities.ASSET_MANAGE,
                                       message=ASSET_MANAGE_PERMISSION_REQUIRED)
    delete_response = yield kvstore.async_kvstore_delete_request(
        collection=ASSETS_COLLECTION_NAME, auth_header=request_context.auth_header,
        params={QUERY: get_query_matching_keys(asset_ids)})
    if delete_response.code != http.OK:
        message = yield delete_response.text()
        raise SpacebridgeApiRequestError('Unable to delete asset_ids={} message={} status_code={}'.format(
            asset_ids, message, delete_response.code), status_code=delete_response.code)
    yield permissions.delete_objects(request_context, asset_ids)
    defer.returnValue(asset_ids)
