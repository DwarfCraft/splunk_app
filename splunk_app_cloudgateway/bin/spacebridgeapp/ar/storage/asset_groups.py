"""
(C) 2020 Splunk Inc. All rights reserved.

Provides access to the AR asset groups KV store collection.
"""
import json

from spacebridgeapp.ar.ar_util import is_non_string_iterable
from spacebridgeapp.ar.data.asset_group_data import AssetGroup
from spacebridgeapp.ar.permissions.async_permissions_client import Capabilities, AccessQuantity, ARObjectType
from spacebridgeapp.ar.storage.queries import get_query_matching_keys
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError, SpacebridgeARPermissionError
from spacebridgeapp.logging.setup_logging import setup_logging
from spacebridgeapp.util.constants import (
    SPACEBRIDGE_APP_NAME, ASSET_GROUPS_COLLECTION_NAME, KEY, QUERY, OR_OPERATOR, ASSET_GROUP, ASSETS_COLLECTION_NAME
)
from twisted.internet import defer
from twisted.web import http

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + '_asset_groups', 'asset_groups')


class AssetGroupAlreadyExists(SpacebridgeApiRequestError):
    def __init__(self, asset_group_id):
        super(AssetGroupAlreadyExists, self).__init__(message='asset_group_id={} already exists'.format(asset_group_id),
                                                      status_code=http.CONFLICT)


@defer.inlineCallbacks
def get_asset_groups(request_context, asset_group_ids, kvstore, permissions, ignore_permissions=False):
    """
    Looks up asset groups from KV store.

    :param request_context: the RequestContext of the request
    :param asset_group_ids: the asset group IDs to look up. If this is None or empty, all are retrieved
    :param kvstore: an AsyncKvStoreClient
    :param permissions: an AsyncArPermissionsClient
    :param ignore_permissions: (optional) whether to skip the permissions check when looking up asset groups. This
                               should only be done when validation is done separately or if the retrieved groups are
                               not sent to the user.
    :return: a list of AssetGroup objects for each asset group retrieved from KV store
    """
    if asset_group_ids and not is_non_string_iterable(asset_group_ids):
        asset_group_ids = [asset_group_ids]

    if not ignore_permissions:
        asset_group_access = yield permissions.get_accessible_objects(request_context, Capabilities.ASSET_GROUP_READ)
        if asset_group_access.quantity == AccessQuantity.NONE:
            defer.returnValue([])
        if asset_group_access.quantity == AccessQuantity.SOME:
            if asset_group_ids:
                asset_group_ids = [asset_group_id for asset_group_id in asset_group_ids
                                   if asset_group_id in asset_group_access.ids]
            else:
                asset_group_ids = list(asset_group_access.ids)

    params = None
    if asset_group_ids:
        params = {QUERY: get_query_matching_keys(asset_group_ids)}
    asset_group_get_response = yield kvstore.async_kvstore_get_request(collection=ASSET_GROUPS_COLLECTION_NAME,
                                                                       auth_header=request_context.auth_header,
                                                                       params=params)
    if asset_group_get_response.code != http.OK:
        message = yield asset_group_get_response.text()
        raise SpacebridgeApiRequestError(
            'Failed to lookup asset groups asset_group_ids={} message={} status_code={}'.format(
                asset_group_ids, message, asset_group_get_response.code), status_code=asset_group_get_response.code)

    asset_groups_json = yield asset_group_get_response.json()
    defer.returnValue([AssetGroup.from_json(asset_group) for asset_group in asset_groups_json])


@defer.inlineCallbacks
def create_asset_group(request_context, asset_group, kvstore, permissions):
    """
    Creates the given asset group.

    :param request_context: the RequestContext of the request
    :param asset_group: the asset group to create
    :param kvstore: an AsyncKvStoreClient
    :param permissions: an AsyncArPermissionsClient
    :raises: AssetGroupAlreadyExists if the given group already exists
    :return: the ID of the created asset group
    """
    yield permissions.check_permission(request_context, Capabilities.ASSET_GROUP_MANAGE)
    create_group_response = yield kvstore.async_kvstore_post_request(collection=ASSET_GROUPS_COLLECTION_NAME,
                                                                     auth_header=request_context.auth_header,
                                                                     data=asset_group.to_json())
    if create_group_response.code == http.CONFLICT:
        raise AssetGroupAlreadyExists(asset_group.asset_group_id)
    if create_group_response.code not in {http.OK, http.CREATED}:
        message = yield create_group_response.text()
        raise SpacebridgeApiRequestError(
            'Failed to create asset group message={} status_code={}'.format(message, create_group_response.code),
            status_code=create_group_response.code)
    created_group_json = yield create_group_response.json()
    created_group_id = created_group_json[KEY]

    yield permissions.register_objects(request_context, ARObjectType.ASSET_GROUP, [created_group_id])

    defer.returnValue(created_group_id)


@defer.inlineCallbacks
def bulk_update_asset_groups(request_context, asset_groups, kvstore, permissions):
    """
    Creates or updates the given list of asset groups.

    :param request_context: the RequestContext of the request
    :param asset_groups: the asset groups to create or update
    :param kvstore: an AsyncKvStoreClient
    :param permissions: an AsyncArPermissionsClient
    :return: the updated asset group IDs
    """
    asset_group_access = yield permissions.get_accessible_objects(request_context, Capabilities.ASSET_GROUP_WRITE)
    if asset_group_access.quantity == AccessQuantity.NONE:
        raise SpacebridgeARPermissionError(
            'User username={} does not have permission to update asset groups'.format(request_context.current_user))

    # Make sure we don't touch any asset groups the user does not have permission to update
    if asset_group_access.quantity == AccessQuantity.SOME:
        asset_group_ids = [asset_group.asset_group_id for asset_group in asset_groups]
        if not all(asset_group_ids):
            # At least one of the specified groups doesn't have an ID so the user intended to create it (not update).
            raise SpacebridgeARPermissionError('Must have asset_group_manage to create asset groups')

        existing_groups = yield get_asset_groups(request_context, asset_group_ids, kvstore, permissions,
                                                 ignore_permissions=True)
        if len(existing_groups) < len(asset_groups):
            raise SpacebridgeARPermissionError('Must have asset_group_manage to create asset groups')

        existing_groups_by_id = {asset_group.asset_group_id: asset_group for asset_group in existing_groups}
        for updated_group in asset_groups:
            if updated_group.asset_group_id in asset_group_access.ids:
                continue

            existing_group = existing_groups_by_id[updated_group.asset_group_id]
            if updated_group != existing_group:
                raise SpacebridgeARPermissionError(
                    'Must have asset_group_write on asset_group_id={} to perform this update.'.format(
                        existing_group.asset_group_id))

    entries = [asset_group.to_dict(jsonify_objects=True) for asset_group in asset_groups]
    updated_asset_group_ids = yield kvstore.async_batch_save_request(collection=ASSET_GROUPS_COLLECTION_NAME,
                                                                     auth_header=request_context.auth_header,
                                                                     entries=entries)
    yield permissions.register_objects(request_context, ARObjectType.ASSET_GROUP, updated_asset_group_ids,
                                       check_if_objects_exist=True)
    defer.returnValue(updated_asset_group_ids)


@defer.inlineCallbacks
def delete_asset_groups(request_context, asset_group_ids, kvstore, permissions):
    """
    Deletes the given asset group and all assets that were members of the group.

    :param request_context: the RequestContext of the request
    :param asset_group_ids: the asset group IDs to delete
    :param kvstore: an AsyncKvStoreClient
    :param permissions: an AsyncArPermissionsClient
    :return: the deleted asset group IDs
    """
    if not asset_group_ids:
        raise SpacebridgeApiRequestError('Must specify asset group IDs when deleting asset groups.',
                                         status_code=http.BAD_REQUEST)
    yield permissions.check_permission(request_context, Capabilities.ASSET_GROUP_MANAGE,
                                       message='Cannot delete asset groups without asset_group_manage.')
    if not is_non_string_iterable(asset_group_ids):
        asset_group_ids = [asset_group_ids]

    # Delete the asset group entries
    delete_groups_response = yield kvstore.async_kvstore_delete_request(
        collection=ASSET_GROUPS_COLLECTION_NAME, auth_header=request_context.auth_header,
        params={QUERY: get_query_matching_keys(asset_group_ids)})
    if delete_groups_response.code != http.OK:
        message = yield delete_groups_response.text()
        raise SpacebridgeApiRequestError(
            'Unable to delete asset_group_ids={} message={} status_code={}'.format(
                asset_group_ids, message, delete_groups_response.code), status_code=delete_groups_response.code)

    # Delete all assets that were members of the deleted groups
    params = {
        QUERY: json.dumps({
            OR_OPERATOR: [
                {ASSET_GROUP: asset_group_id} for asset_group_id in asset_group_ids
            ]
        })
    }
    delete_assets_response = yield kvstore.async_kvstore_delete_request(
        collection=ASSETS_COLLECTION_NAME, auth_header=request_context.auth_header, params=params)
    if delete_assets_response.code != http.OK:
        message = yield delete_groups_response.text()
        raise SpacebridgeApiRequestError(
            'Unable to delete assets with asset_group_ids={} message={} status_code={}'.format(
                asset_group_ids, message, delete_assets_response.code), status_code=delete_assets_response.code)
    yield permissions.delete_objects(request_context, asset_group_ids)
    defer.returnValue(asset_group_ids)
