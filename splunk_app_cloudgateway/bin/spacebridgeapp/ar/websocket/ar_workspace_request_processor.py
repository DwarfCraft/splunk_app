"""
(C) 2019 Splunk Inc. All rights reserved.

Module to process AR Workspace Requests
"""
import base64
import datetime
import itertools
import json
from uuid import uuid4

from spacebridgeapp.util import py23
from google.protobuf.json_format import MessageToJson, MessageToDict, Parse, ParseDict, ParseError
from spacebridgeapp.exceptions.spacebridge_exceptions import (SpacebridgeError, SpacebridgeApiRequestError,
                                                              SpacebridgeARPermissionError)
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.ar.ar_util import wait_for_all
from spacebridgeapp.ar.permissions.async_permissions_client import Capabilities, Access, AccessQuantity, ARObjectType
from spacebridgeapp.ar.storage.queries import get_query_matching_keys
from spacebridgeapp.ar.visualizations.workspace_layout import set_default_layout
from spacebridgeapp.request.dashboard_request_processor import fetch_dashboard_description
from spacebridgeapp.util.constants import (KEY, ORIGINAL_WORKSPACE_FIELD, AR_DASHBOARDS_COLLECTION_NAME, OR_OPERATOR,
                                           QUERY, SPACEBRIDGE_APP_NAME, WORKSPACE_DATA, AR_WORKSPACES_COLLECTION_NAME,
                                           LAST_MODIFIED, VIEW_PERMISSION_REQUIRED, MODIFY_PERMISSION_REQUIRED,
                                           MANAGE_PERMISSION_REQUIRED)
from spacebridgeapp.util.guid_generator import get_guid
from splapp_protocol.augmented_reality_pb2 import ARWorkspaceData, ARWorkspaceAnchored, ARModelData, ARLayout
from twisted.internet import defer
from twisted.web import http

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_ar_workspace_request_processor", "ar_workspace_request_processor")

GEOMETRY_VECTOR = 'geometryVector'
TRANSFORM_MATRIX = 'transformMatrix'
WORKSPACE_VIEW_PERMISSION_REQUIRED = VIEW_PERMISSION_REQUIRED.format(object_type='workspace')
WORKSPACE_MODIFY_PERMISSION_REQUIRED = MODIFY_PERMISSION_REQUIRED.format(object_type='workspace')
WORKSPACE_MANAGE_PERMISSION_REQUIRED = MANAGE_PERMISSION_REQUIRED.format(object_type='workspace')
NOTE_MODIFY_PERMISSION_REQUIRED = MODIFY_PERMISSION_REQUIRED.format(object_type='note')
PLAYBOOK_MODIFY_PERMISSION_REQUIRED = MODIFY_PERMISSION_REQUIRED.format(object_type='playbook')
POSITIONAL_CHANGE_THRESHOLD = 0.0001


class WorkspaceAlreadyExistsException(SpacebridgeError):
    def __init__(self, message):
        super(WorkspaceAlreadyExistsException, self).__init__(message, status_code=http.BAD_REQUEST)


class MissingWorkspaceIDError(SpacebridgeError):
    def __init__(self, message='No workspace ID provided.'):
        super(MissingWorkspaceIDError, self).__init__(message, status_code=http.BAD_REQUEST)


class MissingWorkspaceTitleError(SpacebridgeError):
    def __init__(self, message='No workspace title provided.'):
        super(MissingWorkspaceTitleError, self).__init__(message, status_code=http.BAD_REQUEST)


class NoSuchWorkspaceError(SpacebridgeError):
    def __init__(self, workspace_id):
        super(NoSuchWorkspaceError, self).__init__(message='No such workspace {}'.format(workspace_id),
                                                   status_code=404)


@defer.inlineCallbacks
def process_ar_workspace_set_request_v2(request_context,
                                        client_single_request,
                                        server_single_response,
                                        async_kvstore_client,
                                        async_ar_permissions_client,
                                        async_splunk_client):
    """
    This method processes AR Workspace set requests, and overwrites the workspace
    positioning data in the kvstore

    :param request_context: a request_context.RequestContext
    :param client_single_request: reference client request object
    :param server_single_response: pass-by-reference return object
    :param async_kvstore_client: an async_kvstore_client.AsyncKvStoreClient
    :param async_ar_permissions_client: an async_ar_permissions_client.AsyncArPermissionsClient
    :param async_splunk_client: an async_splunk_client.AsyncSplunkClient
    """
    workspace_data = client_single_request.arWorkspaceSetRequestV2.workspace
    try:
        created_id = yield create_ar_workspace(request_context, async_splunk_client, async_kvstore_client,
                                               async_ar_permissions_client, workspace_data)
        server_single_response.arWorkspaceSetResponseV2.arWorkspaceId = created_id
        defer.returnValue(True)
    except WorkspaceAlreadyExistsException:
        LOGGER.exception('Workspace workspace_id=%s already exists. Attempting to update instead.',
                         workspace_data.arWorkspaceId)
    except SpacebridgeARPermissionError:
        LOGGER.exception('User is not allowed to create workspaces. Attempting to update an existing one instead.')

    if workspace_data.arWorkspaceId:
        updated_id = yield update_ar_workspace(request_context, async_kvstore_client,
                                               async_ar_permissions_client, workspace_data)
        server_single_response.arWorkspaceSetResponseV2.arWorkspaceId = updated_id
    else:
        # The user did not supply a workspace ID to update so they must have intended to create a workspace but do not
        # have permission to do so.
        raise SpacebridgeARPermissionError(message=WORKSPACE_MANAGE_PERMISSION_REQUIRED)


@defer.inlineCallbacks
def process_ar_workspace_get_request_v2(request_context,
                                        client_single_request,
                                        server_single_response,
                                        async_kvstore_client,
                                        async_ar_permissions_client):
    """
    This method processes AR Workspace get requests

    :param request_context:
    :param client_single_request: reference client request object
    :param server_single_response: pass-by-reference return object
    :param async_kvstore_client: an async_kvstore_client.AsyncKvStoreClient
    :param async_ar_permissions_client: an async_ar_permissions_client.AsyncArPermissionsClient
    """
    workspace_ids = client_single_request.arWorkspaceGetRequestV2.arWorkspaceId
    workspaces = yield get_ar_workspaces(request_context,
                                         async_kvstore_client,
                                         async_ar_permissions_client,
                                         workspace_ids)
    del server_single_response.arWorkspaceGetResponseV2.workspace[:]
    server_single_response.arWorkspaceGetResponseV2.workspace.extend(workspaces)


@defer.inlineCallbacks
def process_ar_workspace_delete_request_v2(request_context,
                                           client_single_request,
                                           server_single_response,
                                           async_kvstore_client,
                                           async_ar_permissions_client):
    """
    This method processes AR Workspace delete requests

    :param request_context: a request_context.RequestContext
    :param client_single_request: reference client request object
    :param server_single_response: pass-by-reference return object
    :param async_kvstore_client: an async_kvstore_client.AsyncKvStoreClient
    :param async_ar_permissions_client: an async_ar_permissions_client.AsyncArPermissionsClient
    """
    workspace_ids = client_single_request.arWorkspaceDeleteRequestV2.arWorkspaceId
    yield delete_ar_workspace(request_context, async_kvstore_client, async_ar_permissions_client,
                              workspace_ids)
    server_single_response.arWorkspaceDeleteResponseV2.SetInParent()
    LOGGER.error("Call to AR WORKSPACE DELETE succeeded")


@defer.inlineCallbacks
def process_ar_workspace_image_set_request(request_context,
                                           client_single_request,
                                           server_single_response,
                                           async_kvstore_client,
                                           async_ar_permissions_client):
    """
    This method processes AR Workspace image set requests, overwrites the workspace positioning data
    for the workspace corresponding to the dashboard with the specified image.

    :param request_context:
    :param client_single_request:
    :param server_single_response:
    :param async_kvstore_client:
    :return:
    """
    yield async_ar_permissions_client.check_permission(request_context, Capabilities.WORKSPACE_WRITE,
                                                       message=WORKSPACE_MODIFY_PERMISSION_REQUIRED)
    dashboard_key = client_single_request.arWorkspaceImageSetRequest.arWorkspaceAnchored.key

    if not dashboard_key or not dashboard_key.anchorId:
        raise SpacebridgeApiRequestError("Call to AR workspace IMAGE SET with no anchorId", status_code=400)

    dashboard_id = make_dashboard_name(dashboard_key.dashboardId)
    dashboard_name = make_dashboard_name(dashboard_key.dashboardId, dashboard_key.anchorId)

    # all the ar workspaces with images will have the ARWorkspaceKey object saved with them
    ar_workspace = py23.b64encode_to_str(
        client_single_request.arWorkspaceImageSetRequest.arWorkspaceAnchored.arWorkspace.SerializeToString())
    json_body = {KEY: dashboard_name,
                 ORIGINAL_WORKSPACE_FIELD: dashboard_id,
                 WORKSPACE_DATA: ar_workspace}

    response = yield async_kvstore_client.async_kvstore_post_request(AR_DASHBOARDS_COLLECTION_NAME,
                                                                     data=json.dumps(json_body),
                                                                     auth_header=request_context.auth_header)

    if response.code == http.CONFLICT:
        # in this case the workspace already exists, so make an update post request
        response = yield async_kvstore_client.async_kvstore_post_request(AR_DASHBOARDS_COLLECTION_NAME,
                                                                         data=json.dumps(json_body),
                                                                         auth_header=request_context.auth_header,
                                                                         key_id=dashboard_name)

    message = yield response.text()

    if response.code not in [http.OK, http.CREATED]:
        raise SpacebridgeApiRequestError("Call to AR workspace IMAGE SET failed with code={} message={}"
                                         .format(response.code, message), status_code=response.code)

    LOGGER.info("Call to AR workspace SET succeeded with code={} message={}".format(response.code, message))

    server_single_response.arWorkspaceImageSetResponse.dashboardId.dashboardId = dashboard_key.dashboardId
    server_single_response.arWorkspaceImageSetResponse.dashboardId.anchorId = dashboard_key.anchorId


@defer.inlineCallbacks
def process_ar_workspace_list_request(request_context,
                                      client_single_request,
                                      server_single_response,
                                      async_kvstore_client,
                                      async_ar_permissions_client):
    """
    This method processes AR Workspace list get requests, returning the ARWorkspaceList protobuf
    objects stored in the kvstore within the arWorkspaceListResponse

    :param request_context:
    :param client_single_request: reference client request object
    :param server_single_response: pass-by-reference return object
    :param async_kvstore_client:
    """
    yield async_ar_permissions_client.check_permission(request_context, Capabilities.WORKSPACE_READ,
                                                       message=WORKSPACE_VIEW_PERMISSION_REQUIRED)
    dashboard_name = make_dashboard_name(client_single_request.arWorkspaceListRequest.dashboardId)
    query = {OR_OPERATOR: [{KEY: dashboard_name}, {ORIGINAL_WORKSPACE_FIELD: dashboard_name}]}
    response = yield async_kvstore_client.async_kvstore_get_request(AR_DASHBOARDS_COLLECTION_NAME,
                                                                    request_context.auth_header,
                                                                    params={QUERY: json.dumps(query)})

    message = yield response.text()

    if response.code != http.OK:
        raise SpacebridgeApiRequestError("Call to AR workspace LIST failed with code={} message={}"
                                         .format(response.code, message), status_code=response.code)

    LOGGER.info("Call to AR workspace LIST succeeded with code={} message={}".format(response.code, message))

    response_list = yield response.json()
    if not response_list:
        raise SpacebridgeApiRequestError("Call to AR workspace LIST returned empty results message={}"
                                         .format(message), status_code=204)

    workspaces = []
    construct_ar_workspace_list(response_list, dashboard_name, workspaces)

    del server_single_response.arWorkspaceListResponse.workspaceList.arWorkspaces[:]
    server_single_response.arWorkspaceListResponse.workspaceList.arWorkspaces.extend(workspaces)

    LOGGER.info("AR workspace successfully decoded code={} message={}".format(response.code, message))


def process_ar_workspace_format_request(request_context, client_single_request, server_single_response):
    workspace = client_single_request.arWorkspaceFormatRequest.workspace
    workspace = set_default_layout(workspace)
    server_single_response.arWorkspaceFormatResponse.workspace.CopyFrom(workspace)


@defer.inlineCallbacks
def get_ar_workspaces(request_context, async_kvstore_client, async_ar_permissions_client=None, workspace_ids=None,
                      json_format=False):
    """Looks up the given workspace_ids from KV store."""
    workspace_access, note_access, playbook_access = yield async_ar_permissions_client.get_accessible_objects(
        request_context, Capabilities.WORKSPACE_READ, Capabilities.NOTE_READ, Capabilities.PLAYBOOK_READ)
    if workspace_access.quantity == AccessQuantity.NONE:
        defer.returnValue([])
    elif workspace_access.quantity == AccessQuantity.SOME:
        workspace_ids = ([workspace_id for workspace_id in workspace_ids if workspace_id in workspace_access.ids]
                         if workspace_ids else workspace_access.ids)

    workspaces_json = yield _lookup_workspaces(request_context.auth_header, async_kvstore_client, workspace_ids)
    workspaces = [parse_workspace_data(workspace_json[WORKSPACE_DATA]) for workspace_json in workspaces_json]
    for workspace in workspaces:
        _strip_workspace_component(workspace, note_access, lambda note: note.id, 'notes')
        _strip_workspace_component(workspace, note_access, lambda note: note.id, 'labels')
        _strip_workspace_component(workspace, playbook_access, lambda playbook: playbook.id, 'arPlaybooks')

    if not json_format:
        defer.returnValue(workspaces)

    formatted_json = []
    for json_workspace, proto_workspace in zip(workspaces_json, workspaces):
        formatted_workspace = {
            KEY: json_workspace[KEY],
            WORKSPACE_DATA: MessageToDict(proto_workspace, including_default_value_fields=True)
        }
        if LAST_MODIFIED in json_workspace:
            formatted_workspace[LAST_MODIFIED] = json_workspace[LAST_MODIFIED]
        formatted_json.append(formatted_workspace)
    defer.returnValue(formatted_json)


def parse_workspace_data(workspace_data):
    try:
        return Parse(workspace_data, ARWorkspaceData(), ignore_unknown_fields=True)
    except ParseError:
        return ParseDict(workspace_data, ARWorkspaceData(), ignore_unknown_fields=True)


@defer.inlineCallbacks
def _lookup_workspaces(auth_header, async_kvstore_client, workspace_ids=None, as_protobuf=False):
    params = None
    if workspace_ids:
        params = {QUERY: get_query_matching_keys(workspace_ids)}
    kvstore_response = yield async_kvstore_client.async_kvstore_get_request(collection=AR_WORKSPACES_COLLECTION_NAME,
                                                                            auth_header=auth_header,
                                                                            params=params)
    if kvstore_response.code != http.OK:
        message = yield kvstore_response.text()
        raise SpacebridgeApiRequestError("Failed to lookup AR workspaces from KV store with code={} message={}".format(
            kvstore_response.code, message), status_code=kvstore_response.code)

    workspaces = yield kvstore_response.json()
    if as_protobuf:
        workspaces = [parse_workspace_data(workspace[WORKSPACE_DATA]) for workspace in workspaces]
    defer.returnValue(workspaces)


def _strip_workspace_component(workspace, access, id_func, field_name):
    if access.quantity == AccessQuantity.ALL:
        return
    field = getattr(workspace, field_name)
    if access.quantity == AccessQuantity.NONE:
        del getattr(workspace, field_name)[:]
    if access.quantity == AccessQuantity.SOME:
        viewable_objects = [obj for obj in field if id_func(obj) in access.ids]
        del field[:]
        field.extend(viewable_objects)


@defer.inlineCallbacks
def create_ar_workspace(request_context, async_splunk_client, async_kvstore_client, async_ar_permissions_client,
                        ar_workspace_data_pb, dashboard_id=None):
    """Creates a new KV store entry for the given ar_workspace_data_pb.

    If no workspace ID is present in ar_workspace_data_pb a random one will be generated and added to the passed in
    workspace data.

    :param request_context: A RequestContext for the calling request
    :param async_splunk_client: An AsyncSplunkClient for contacting Splunk REST APIs
    :param async_kvstore_client: An AsyncKvStoreClient for writing the new workspace to KV store
    :param async_ar_permissions_client: An AsyncARPermissionsClient for checking workspace permissions
    :param ar_workspace_data_pb: The ARWorkspaceData to write to KV store
    :param dashboard_id: (Optional) The dashboard ID (str) of the dashboard to use to initialize the workspace panel
                         positional data. If none is present, the workspace will be stored exactly as is.
    """
    yield async_ar_permissions_client.check_permission(request_context, Capabilities.WORKSPACE_MANAGE,
                                                       message=WORKSPACE_MANAGE_PERMISSION_REQUIRED)
    if not ar_workspace_data_pb.title:
        raise MissingWorkspaceTitleError()
    if not ar_workspace_data_pb.arWorkspaceId:
        ar_workspace_data_pb.arWorkspaceId = get_guid()
    _populate_component_ids(ar_workspace_data_pb)

    if dashboard_id and not ar_workspace_data_pb.children:
        dashboard = yield fetch_dashboard_description(request_context=request_context,
                                                      dashboard_id=dashboard_id,
                                                      async_kvstore_client=async_kvstore_client,
                                                      async_splunk_client=async_splunk_client)
        dashboard = dashboard.to_protobuf()
        panel_count = sum((len(row.panels) for row in dashboard.definition.rows))
        del ar_workspace_data_pb.children[:]
        ar_workspace_data_pb.children.extend([ARModelData(arLayout=ARLayout(index=i)) for i in range(panel_count)])
        ar_workspace_data_pb = set_default_layout(ar_workspace_data_pb)

    workspace = serialize_workspace_for_storage(ar_workspace_data_pb)
    response = yield async_kvstore_client.async_kvstore_post_request(AR_WORKSPACES_COLLECTION_NAME,
                                                                     data=json.dumps(workspace),
                                                                     auth_header=request_context.auth_header)
    if response.code == http.CONFLICT:
        message = yield response.text()
        raise WorkspaceAlreadyExistsException(message)
    elif response.code not in {http.OK, http.CREATED}:
        message = yield response.text()
        raise SpacebridgeApiRequestError(
            message='Failed to create workspace id={} message={}'.format(ar_workspace_data_pb.arWorkspaceId, message),
            status_code=response.code)
    yield _set_permissions_for_workspace(request_context, async_kvstore_client, async_ar_permissions_client,
                                         ar_workspace_data_pb)
    defer.returnValue(ar_workspace_data_pb.arWorkspaceId)


@defer.inlineCallbacks
def update_ar_workspace(request_context, async_kvstore_client, async_ar_permissions_client, ar_workspace_data_pb):
    """Overwrites an existing workspace with the data from ar_workspace_data_pb."""
    if not ar_workspace_data_pb.arWorkspaceId:
        raise MissingWorkspaceIDError()
    if not ar_workspace_data_pb.title:
        raise MissingWorkspaceTitleError()
    _populate_component_ids(ar_workspace_data_pb)
    workspace_id = ar_workspace_data_pb.arWorkspaceId

    existing_workspaces = yield _lookup_workspaces(request_context.auth_header, async_kvstore_client, [workspace_id],
                                                   as_protobuf=True)
    if not existing_workspaces:
        raise NoSuchWorkspaceError(workspace_id=workspace_id)
    existing_workspace = existing_workspaces[0]

    if client_supports_object_capabilities(request_context.client_version):
        yield _validate_workspace_updates(request_context, existing_workspace, ar_workspace_data_pb,
                                          async_ar_permissions_client)
    else:
        yield _validate_workspace_updates_old(request_context, existing_workspace, ar_workspace_data_pb,
                                              async_ar_permissions_client)
    serialized_workspace = serialize_workspace_for_storage(ar_workspace_data_pb)
    update_response = yield async_kvstore_client.async_kvstore_post_request(collection=AR_WORKSPACES_COLLECTION_NAME,
                                                                            data=json.dumps(serialized_workspace),
                                                                            auth_header=request_context.auth_header,
                                                                            key_id=ar_workspace_data_pb.arWorkspaceId)
    if update_response.code != http.OK:
        message = yield update_response.text()
        raise SpacebridgeApiRequestError(
            'Failed to update workspace id={} message={}'.format(ar_workspace_data_pb.arWorkspaceId, message),
            status_code=update_response.code)
    yield _set_permissions_for_workspace(request_context, async_kvstore_client, async_ar_permissions_client,
                                         ar_workspace_data_pb, existing_workspace)
    defer.returnValue(ar_workspace_data_pb.arWorkspaceId)


def _populate_component_ids(ar_workspace_data_pb):
    for note in itertools.chain(ar_workspace_data_pb.notes, ar_workspace_data_pb.labels):
        if not note.id:
            note.id = _create_note_id()
    for playbook in ar_workspace_data_pb.arPlaybooks:
        if not playbook.id:
            playbook.id = _create_playbook_id()


@defer.inlineCallbacks
def _set_permissions_for_workspace(request_context, kvstore, permissions, updated_workspace, existing_workspace=None):
    all_notes = {note.id for note in itertools.chain(updated_workspace.notes, updated_workspace.labels)}
    all_playbooks = {playbook.id for playbook in updated_workspace.arPlaybooks}

    notes_to_add, playbooks_to_add = set(all_notes), set(all_playbooks)
    notes_to_remove, playbooks_to_remove = set(), set()
    if existing_workspace:
        existing_notes = {note.id for note in itertools.chain(existing_workspace.notes, existing_workspace.labels)}
        existing_playbooks = {playbook.id for playbook in existing_workspace.arPlaybooks}

        notes_to_add -= existing_notes
        playbooks_to_add -= existing_playbooks
        notes_to_remove = existing_notes - all_notes
        playbooks_to_remove = existing_playbooks - all_playbooks

    updates = []
    if not existing_workspace:
        updates.append(permissions.register_objects(request_context, ARObjectType.WORKSPACE,
                                                    [updated_workspace.arWorkspaceId]))
    if notes_to_add:
        updates.append(permissions.register_objects(request_context, ARObjectType.NOTE, notes_to_add,
                                                    check_if_objects_exist=True))
    if playbooks_to_add:
        updates.append(permissions.register_objects(request_context, ARObjectType.PLAYBOOK, playbooks_to_add,
                                                    check_if_objects_exist=True))
    if notes_to_remove:
        updates.append(permissions.delete_objects(request_context, notes_to_remove))

    if playbooks_to_remove:
        updates.append(permissions.delete_objects(request_context, playbooks_to_remove))

    yield wait_for_all(updates, raise_on_first_exception=True)


@defer.inlineCallbacks
def _validate_workspace_updates(request_context, existing_workspace, updated_workspace, permissions):
    can_edit_workspace = yield permissions.check_object_permission(request_context, Capabilities.WORKSPACE_WRITE,
                                                                   updated_workspace.arWorkspaceId,
                                                                   raise_on_missing=False)
    can_manage_notes, can_manage_playbooks = yield permissions.check_multiple_permissions(
        request_context, [Capabilities.NOTE_MANAGE, Capabilities.PLAYBOOK_MANAGE], raise_on_missing=False)
    if not can_edit_workspace and not all([
        existing_workspace.title == updated_workspace.title,
        existing_workspace.transformMatrix == updated_workspace.transformMatrix,
        existing_workspace.geometryVector == updated_workspace.geometryVector,
        existing_workspace.children == updated_workspace.children,
        can_manage_notes or _compare_positional_data(existing_workspace.notes, updated_workspace.notes,
                                                     lambda note: note.id),
        can_manage_notes or _compare_positional_data(existing_workspace.labels, updated_workspace.labels,
                                                     lambda note: note.id),
        can_manage_playbooks or _compare_positional_data(existing_workspace.arPlaybooks, updated_workspace.arPlaybooks,
                                                         lambda playbook: playbook.id),
    ]):
        raise SpacebridgeARPermissionError(WORKSPACE_MODIFY_PERMISSION_REQUIRED)

    # If the user can manage notes and playbooks there is no point in looking up which specific notes and playbooks
    # they can modify.
    if can_manage_notes and can_manage_playbooks:
        defer.returnValue(None)

    (note_read_access, note_write_access, playbook_read_access,
     playbook_write_access) = yield permissions.get_accessible_objects(
        request_context, Capabilities.NOTE_READ, Capabilities.NOTE_WRITE, Capabilities.PLAYBOOK_READ,
        Capabilities.PLAYBOOK_WRITE)
    if not can_manage_notes:
        validation = (_validate_workspace_component_updates(existing_workspace.notes, updated_workspace.notes,
                                                            note_read_access, note_write_access, lambda note: note.id)
                      and _validate_workspace_component_updates(existing_workspace.labels, updated_workspace.labels,
                                                                note_read_access, note_write_access,
                                                                lambda note: note.id))
        if not validation:
            raise SpacebridgeARPermissionError(NOTE_MODIFY_PERMISSION_REQUIRED)
    if not can_manage_playbooks:
        validation = _validate_workspace_component_updates(existing_workspace.arPlaybooks,
                                                           updated_workspace.arPlaybooks, playbook_read_access,
                                                           playbook_write_access, lambda playbook: playbook.id)
        if not validation:
            raise SpacebridgeARPermissionError(PLAYBOOK_MODIFY_PERMISSION_REQUIRED)


def _validate_workspace_component_updates(original, updated, read_access, write_access, id_func):
    updated_by_id = {id_func(u) for u in updated}
    components_to_add = []
    for o in original:
        o_id = id_func(o)
        # Make sure the user did not delete any existing notes or playbooks.
        if o_id in read_access.ids and o_id not in updated_by_id:
            LOGGER.debug('User attempted to delete note or playbook id=%s', o_id)
            return False
        # Now make sure we add back in any notes or playbooks that the user could not view so they aren't accidentally
        # removed.
        elif o_id not in read_access.ids:
            components_to_add.append(o)

    original_by_id = {id_func(orig): orig for orig in original}
    for component in updated:
        component_id = id_func(component)
        # The user must have added the note or playbook
        if component_id not in original_by_id:
            LOGGER.debug('User attempted to add a note or playbook')
            return False

        # Both the updated workspace and the original workspace have this note or playbook and they are now different.
        if component_id not in write_access.ids and not _compare_message_contents(original_by_id[component_id],
                                                                                  component):
            LOGGER.debug('User attempted to update note or playbook id=%s', component_id)
            return False

    updated.extend(components_to_add)
    return True


def _compare_positional_data(existing, updated, id_func=None):
    existing_by_id = {id_func(e) if id_func else i: e for i, e in enumerate(existing)}
    for i, u in enumerate(updated):
        u_id = id_func(u) if id_func else i
        if u_id in existing_by_id and not _compare_positional_data_for_message(existing_by_id[u_id], u):
            return False
    return True


def _compare_positional_data_for_message(existing, updated):
    for descriptor in existing.DESCRIPTOR.fields:
        name = descriptor.name
        e_value = getattr(existing, name)
        u_value = getattr(updated, name)
        if name in {GEOMETRY_VECTOR, TRANSFORM_MATRIX} and not _fuzzy_compare_positional_data(e_value, u_value):
            return False
        if descriptor.type == descriptor.TYPE_MESSAGE and descriptor.label == descriptor.LABEL_REPEATED:
            for e, u in zip(e_value, u_value):
                if not _compare_positional_data_for_message(e, u):
                    return False
        elif descriptor.type == descriptor.TYPE_MESSAGE and not _compare_positional_data_for_message(e_value, u_value):
            return False

    return True


def _fuzzy_compare_positional_data(first_positional_data, second_positional_data):
    for descriptor in first_positional_data.DESCRIPTOR.fields:
        name = descriptor.name
        f_value = getattr(first_positional_data, name)
        s_value = getattr(second_positional_data, name)
        if descriptor.type == descriptor.TYPE_FLOAT and abs(f_value - s_value) > POSITIONAL_CHANGE_THRESHOLD:
            return False

        if descriptor.type == descriptor.TYPE_MESSAGE and not _fuzzy_compare_positional_data(f_value, s_value):
            return False

    return True


def _compare_message_contents(existing, updated, ignore_ids=False):
    for descriptor in existing.DESCRIPTOR.fields:
        if descriptor.name in {GEOMETRY_VECTOR, TRANSFORM_MATRIX}:
            continue

        if ignore_ids and descriptor.name in {'id', 'playbookId'}:
            continue

        if descriptor.type == descriptor.TYPE_MESSAGE:
            e = getattr(existing, descriptor.name)
            u = getattr(updated, descriptor.name)
            if descriptor.label == descriptor.LABEL_REPEATED:
                if len(e) != len(u):
                    return False
                for e_entry, u_entry in zip(e, u):
                    if not _compare_message_contents(e_entry, u_entry):
                        return False
            else:
                if not _compare_message_contents(e, u):
                    return False
        elif getattr(existing, descriptor.name) != getattr(updated, descriptor.name):
            return False

    return True


@defer.inlineCallbacks
def _validate_workspace_updates_old(request_context, existing, updated, permissions):
    capabilities_to_check = [
        Capabilities.WORKSPACE_WRITE,
        Capabilities.NOTE_READ,
        Capabilities.NOTE_WRITE,
        Capabilities.NOTE_MANAGE,
        Capabilities.PLAYBOOK_READ,
        Capabilities.PLAYBOOK_WRITE,
        Capabilities.PLAYBOOK_MANAGE
    ]
    (user_can_modify_workspaces, user_can_view_notes, user_can_modify_notes,
     user_can_manage_notes, user_can_view_playbooks, user_can_modify_playbooks,
     user_can_manage_playbooks) = yield permissions.check_multiple_permissions(
        request_context, capabilities_to_check, message=WORKSPACE_MODIFY_PERMISSION_REQUIRED)

    if not user_can_modify_workspaces:
        workspace_checks = [
            existing.title == updated.title,
            existing.transformMatrix == updated.transformMatrix,
            existing.geometryVector == updated.geometryVector,
            existing.children == updated.children,
            user_can_manage_notes or _compare_positional_data(existing.notes, updated.notes),
            user_can_manage_notes or _compare_positional_data(existing.labels, updated.labels),
            user_can_manage_playbooks or _compare_positional_data(existing.arPlaybooks, updated.arPlaybooks),
        ]
        if not all(workspace_checks):
            raise SpacebridgeARPermissionError(WORKSPACE_MODIFY_PERMISSION_REQUIRED)

    if not user_can_view_notes and len(updated.notes) == 0 and len(updated.labels) == 0:
        updated.notes.extend(existing.notes)
        updated.labels.extend(existing.labels)
    elif not all([
        _check_workspace_component_old(existing.notes, updated.notes, user_can_modify_notes,
                                       user_can_manage_notes),
        _check_workspace_component_old(existing.labels, updated.labels, user_can_modify_notes,
                                       user_can_manage_notes),
    ]):
        raise SpacebridgeARPermissionError(NOTE_MODIFY_PERMISSION_REQUIRED)

    if not user_can_view_playbooks and len(updated.arPlaybooks) == 0:
        updated.arPlaybooks.extend(existing.arPlaybooks)
    elif not all([
        _check_workspace_component_old(existing.arPlaybooks, updated.arPlaybooks,
                                       user_can_modify_playbooks, user_can_manage_playbooks),
    ]):
        raise SpacebridgeARPermissionError(PLAYBOOK_MODIFY_PERMISSION_REQUIRED)


def _check_workspace_component_old(existing, updated, can_edit, can_manage):
    if can_manage:
        return True
    if len(existing) != len(updated):
        return False
    if not can_edit:
        for e, u in zip(existing, updated):
            if not _compare_message_contents(e, u, ignore_ids=True):
                return False
    return True


def serialize_workspace_for_storage(ar_workspace_data_pb, last_modified_time=None):
    _populate_component_ids(ar_workspace_data_pb)
    return {
        KEY: ar_workspace_data_pb.arWorkspaceId,
        WORKSPACE_DATA: MessageToJson(ar_workspace_data_pb, including_default_value_fields=True),
        LAST_MODIFIED: last_modified_time or str(datetime.datetime.utcnow().strftime('%s'))
    }


def _create_note_id():
    return str(uuid4())


def _create_playbook_id():
    return str(uuid4())


@defer.inlineCallbacks
def delete_ar_workspace(request_context, async_kvstore_client, async_ar_permissions_client, workspace_ids):
    """Deletes one or more workspaces from KV store by ID."""
    if not workspace_ids:
        raise SpacebridgeApiRequestError('Must specify workspace IDs to delete.', status_code=http.BAD_REQUEST)

    yield async_ar_permissions_client.check_permission(request_context, Capabilities.WORKSPACE_MANAGE,
                                                       message=WORKSPACE_MANAGE_PERMISSION_REQUIRED)

    workspaces_to_delete = yield _lookup_workspaces(request_context.auth_header, async_kvstore_client, workspace_ids,
                                                    as_protobuf=True)
    note_ids, playbook_ids = [], []
    for workspace in workspaces_to_delete:
        note_ids.extend([note.id for note in itertools.chain(workspace.notes, workspace.labels)])
        playbook_ids.extend([playbook.id for playbook in workspace.arPlaybooks])

    response = yield async_kvstore_client.async_kvstore_delete_request(
        collection=AR_WORKSPACES_COLLECTION_NAME, auth_header=request_context.auth_header,
        params={QUERY: get_query_matching_keys(workspace_ids)})
    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError("Call to AR WORKSPACE DELETE failed with code={} message={}".format(
            response.code, message), status_code=response.code)

    ids_to_remove = list(workspace_ids) + list(note_ids) + list(playbook_ids)
    permissions_updates = [async_ar_permissions_client.delete_objects(request_context, ids_to_remove)]
    yield wait_for_all(permissions_updates, raise_on_first_exception=True)

    defer.returnValue(workspace_ids)


def construct_ar_workspace_list(response_list, dashboard_name, workspaces):
    """Adds the info to each workspace in response_list and adds them to workspaces."""
    for workspace in response_list:
        workspace_string = base64.b64decode(workspace[WORKSPACE_DATA])
        anchored_workspace = ARWorkspaceAnchored()
        anchored_workspace.arWorkspace.ParseFromString(workspace_string)
        anchored_workspace.key.dashboardId = dashboard_name
        anchored_workspace.key.anchorId = get_anchor_from_key(workspace[KEY], dashboard_name)
        workspaces.append(anchored_workspace)


def make_dashboard_name(dashboard_id, anchor_id=None):
    """Gets the dashboard name from its ID and anchor."""
    dashboard_name = dashboard_id.split('/')[-1]

    if anchor_id:
        dashboard_name = "{}_{}".format(dashboard_name, anchor_id)

    return dashboard_name


def get_anchor_from_key(key, dashboard_name):
    """Generates an anchor from the given key and dashboard name."""
    anchor_id = key.replace(dashboard_name + "_", "")
    anchor_id = anchor_id.replace(dashboard_name, "")
    return anchor_id


def client_supports_object_capabilities(client_version_string):
    if not client_version_string:
        return True
    version_parts = client_version_string.split('.')
    if len(version_parts) < 2:
        return True
    major, minor = int(version_parts[0]), int(version_parts[1])
    return (major, minor) >= (2, 3)
