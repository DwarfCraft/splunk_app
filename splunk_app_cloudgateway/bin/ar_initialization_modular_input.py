"""
(C) 2020 Splunk Inc. All rights reserved.

Applies one-time setup required for AR KV store tables to function properly for newly added features or version changes
that may not play nicely with one another.
"""
import itertools
import json
import time

# Required for libraries to be loaded correctly. Must be first among spacebridgeapp imports.
from spacebridgeapp.util import py23
from spacebridgeapp.ar.permissions.async_permissions_client import (
    AR_CAPABILITIES_COLLECTION, ARObjectType, make_public_capabilities_documents, ROLE, AR_PUBLIC_WRITE_ROLE,
    AR_PUBLIC_READ_ROLE
)
from spacebridgeapp.ar.websocket.ar_workspace_request_processor import (
    parse_workspace_data, serialize_workspace_for_storage
)
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeError
from spacebridgeapp.logging.setup_logging import setup_logging
from spacebridgeapp.messages.request_context import RequestContext
from spacebridgeapp.request.splunk_auth_header import SplunkAuthHeader
from spacebridgeapp.rest.clients.async_client_factory import AsyncClientFactory
from spacebridgeapp.util.splunk_utils.statestore import StateStore
from spacebridgeapp.util.constants import (
    SPACEBRIDGE_APP_NAME, WORKSPACE_DATA, LAST_MODIFIED, AR_WORKSPACES_COLLECTION_NAME, LIMIT, SKIP,
    ASSETS_COLLECTION_NAME, ASSET_GROUPS_COLLECTION_NAME, AR_GEOFENCES_COLLECTION_NAME, AR_BEACONS_COLLECTION_NAME, KEY,
    NAME, ENTRY, QUERY, AND_OPERATOR, NOT_EQUAL
)
from spacebridgeapp.util.splunk_utils.common import modular_input_should_run
from splunk import rest
from solnlib import modular_input
from twisted.internet import defer, task
from twisted.web import http

LOGGER = setup_logging(logfile_name='{}_modular_input.log'.format(SPACEBRIDGE_APP_NAME),
                       logger_name='ar_modular_input')

# A single workspace can get big quickly. A workspace for the Cloud Gateway Status dashboard is at least 20KB and
# would be even larger with notes or playbooks. For that reason we only read in and process 500 at a time. I suspect
# very few if any customers have over 500 workspaces in their deployments so this will in most cases cause only a
# few KV store requests.
WORKSPACE_BATCH_SIZE = 500
ASSET_AND_GROUP_BATCH_SIZE = 3000
BEACON_AND_GEOFENCE_BATCH_SIZE = 5000
CAPABILITIES_BATCH_SIZE = 5000


class ARModularInput(modular_input.ModularInput):
    title = 'AR Modular Input'
    description = ('Applies offline updates to AR KV store tables for new features, version changes, and keeping things'
                   ' in sync with dependencies outside of AR.')
    app = 'Splunk App Cloud Gateway'
    name = 'splunkappcloudgateway'
    use_kvstore_checkpointer = False
    use_hec_event_writer = False

    def do_run(self, inputs):
        """
        The entry point for the modular input.

        :param inputs: The command line arguments used when running this modular input. See the parent method definition
                       for more details.
        """
        # noinspection PyBroadException
        try:
            if not modular_input_should_run(self.session_key, LOGGER):
                LOGGER.debug('The AR modular input will not run on this host.')
                return

            uri = rest.makeSplunkdUri()
            _wait_for_kvstore_to_start(uri=uri, session_key=self.session_key, timeout_seconds=30)

            task.react(self._run_initialization, [AsyncClientFactory(uri)])
        except SystemExit as e:
            if e.code != 0:
                LOGGER.exception('Exited AR modular input with non-zero exit_code=%d message=%s',
                                 e.code, e.message)
            else:
                LOGGER.debug('Successfully ran the AR initialization modular input.')
        except Exception:
            LOGGER.exception('Unhandled exception while running AR modular input.')

    @defer.inlineCallbacks
    def _run_initialization(self, unused_reactor, async_client_factory):
        """
        Runs each initialization step required for the AR collections to run properly.

        :param unused_reactor: A Twisted reactor passed as an argument when called with task.react
        :param async_client_factory: An AsyncClientFactory for instantiating other async clients
        """
        try:
            auth_header = SplunkAuthHeader(self.session_key)
            kvstore = async_client_factory.kvstore_client()
            permissions = async_client_factory.ar_permissions_client()
            splunk = async_client_factory.splunk_client()
            yield init_workspace_component_ids(kvstore, auth_header)
            yield init_capabilities_collection(kvstore, auth_header)
            yield cleanup_deleted_roles(splunk, kvstore, permissions, auth_header)
        except Exception as e:
            LOGGER.exception('Unhandled exception during AR modular input steps.')
            raise e
        defer.returnValue(True)


@defer.inlineCallbacks
def init_workspace_component_ids(kvstore, auth_header, batch_size=None):
    workspaces_to_update = []
    start_entry_index = 0
    batch_size = batch_size or WORKSPACE_BATCH_SIZE
    while True:
        workspace_get_response = yield kvstore.async_kvstore_get_request(
            auth_header=auth_header, collection=AR_WORKSPACES_COLLECTION_NAME, params={SKIP: start_entry_index,
                                                                                       LIMIT: batch_size})
        if workspace_get_response.code != http.OK:
            message = yield workspace_get_response.text()
            LOGGER.error('Failed to load workspaces message=%s status_code=%d', message, workspace_get_response.code)
            continue

        workspaces = yield workspace_get_response.json()
        if not workspaces:
            break

        start_entry_index += batch_size

        for workspace in workspaces:
            should_workspace_be_updated = False
            workspace_pb = parse_workspace_data(workspace[WORKSPACE_DATA])
            for note in itertools.chain(workspace_pb.notes, workspace_pb.labels):
                if not note.id:
                    should_workspace_be_updated = True
                    break

            if not should_workspace_be_updated:
                for playbook in workspace_pb.arPlaybooks:
                    if not playbook.id:
                        should_workspace_be_updated = True
                        break

            if should_workspace_be_updated:
                # This will automatically populate any note or playbook IDs if they are not present.
                serialized_workspace = serialize_workspace_for_storage(
                    workspace_pb, last_modified_time=workspace.get(LAST_MODIFIED))
                workspaces_to_update.append(serialized_workspace)

        if len(workspaces_to_update) >= batch_size:
            yield kvstore.async_batch_save_request(auth_header=auth_header, entries=workspaces_to_update,
                                                   collection=AR_WORKSPACES_COLLECTION_NAME)
            del workspaces_to_update[:]

    # There are still some workspaces left to be updated
    if workspaces_to_update:
        yield kvstore.async_batch_save_request(auth_header=auth_header, entries=workspaces_to_update,
                                               collection=AR_WORKSPACES_COLLECTION_NAME)
    LOGGER.debug('Finished writing note IDs.')


@defer.inlineCallbacks
def init_capabilities_collection(kvstore, auth_header, batch_size=None):
    # If there are any entries in the ar_capabilities collection then we know the things have already been initialized
    # and we shouldn't do
    should_init_capabilities_collection = yield _check_should_init_capabilities_collection(kvstore, auth_header)
    if not should_init_capabilities_collection:
        LOGGER.debug('AR capabilities collection is already initialized.')
        return

    capabilities_documents = []

    # Create capabilities entries for workspaces, playbooks, and notes
    yield _buffered_write_capability_entries_for_objects(
        kvstore=kvstore,
        auth_header=auth_header,
        capabilities_documents=capabilities_documents,
        collection=AR_WORKSPACES_COLLECTION_NAME,
        batch_size=batch_size or WORKSPACE_BATCH_SIZE,
        object_type=ARObjectType.WORKSPACE,
        object_to_capability_doc_fn=_generate_capability_entries_from_workspaces
    )

    # Create capabilities entries for assets
    yield _buffered_write_capability_entries_for_objects(
        kvstore=kvstore,
        auth_header=auth_header,
        capabilities_documents=capabilities_documents,
        collection=ASSETS_COLLECTION_NAME,
        batch_size=batch_size or ASSET_AND_GROUP_BATCH_SIZE,
        object_type=ARObjectType.ASSET,
        object_to_capability_doc_fn=_generate_capability_entries_for_single_id_object
    )

    # Create capabilities entries for asset groups
    yield _buffered_write_capability_entries_for_objects(
        kvstore=kvstore,
        auth_header=auth_header,
        capabilities_documents=capabilities_documents,
        collection=ASSET_GROUPS_COLLECTION_NAME,
        batch_size=batch_size or ASSET_AND_GROUP_BATCH_SIZE,
        object_type=ARObjectType.ASSET_GROUP,
        object_to_capability_doc_fn=_generate_capability_entries_for_single_id_object
    )

    # Create capabilities entries for geofences
    yield _buffered_write_capability_entries_for_objects(
        kvstore=kvstore,
        auth_header=auth_header,
        capabilities_documents=capabilities_documents,
        collection=AR_GEOFENCES_COLLECTION_NAME,
        batch_size=batch_size or BEACON_AND_GEOFENCE_BATCH_SIZE,
        object_type=ARObjectType.GEOFENCE,
        object_to_capability_doc_fn=_generate_capability_entries_for_single_id_object
    )

    # Create capabilities entries for beacons
    yield _buffered_write_capability_entries_for_objects(
        kvstore=kvstore,
        auth_header=auth_header,
        capabilities_documents=capabilities_documents,
        collection=AR_BEACONS_COLLECTION_NAME,
        batch_size=batch_size or BEACON_AND_GEOFENCE_BATCH_SIZE,
        object_type=ARObjectType.BEACON,
        object_to_capability_doc_fn=_generate_capability_entries_for_single_id_object
    )

    if capabilities_documents:
        yield kvstore.async_batch_save_request(auth_header=auth_header, entries=capabilities_documents,
                                               collection=AR_CAPABILITIES_COLLECTION)


@defer.inlineCallbacks
def _buffered_write_capability_entries_for_objects(kvstore, auth_header, capabilities_documents, collection, batch_size,
                                                   object_type, object_to_capability_doc_fn):
    start_entry_index = 0
    while True:
        get_response = yield kvstore.async_kvstore_get_request(collection=collection, auth_header=auth_header,
                                                               params={SKIP: start_entry_index, LIMIT: batch_size})
        if get_response.code != http.OK:
            message = yield get_response.text()
            LOGGER.error('Failed to load %s(s) message=%s status_code=%d', object_type, message, get_response.code)
            continue

        retrieved_documents = yield get_response.json()
        if not retrieved_documents:
            return

        start_entry_index += batch_size

        for document in retrieved_documents:
            for capability_document in object_to_capability_doc_fn(document, object_type):
                capabilities_documents.append(capability_document)
                if len(capabilities_documents) >= CAPABILITIES_BATCH_SIZE:
                    yield kvstore.async_batch_save_request(auth_header=auth_header, entries=capabilities_documents,
                                                           collection=AR_CAPABILITIES_COLLECTION)
                    del capabilities_documents[:]


def _generate_capability_entries_for_single_id_object(document, object_type):
    object_id = document[KEY]
    return make_public_capabilities_documents(object_type, object_id)


def _generate_capability_entries_from_workspaces(workspace, unused_object_type):
    documents = []
    workspace_pb = parse_workspace_data(workspace[WORKSPACE_DATA])

    # Documents for the actual workspace
    documents.extend(make_public_capabilities_documents(ARObjectType.WORKSPACE, workspace_pb.arWorkspaceId))

    # Documents for any embedded notes
    for note in itertools.chain(workspace_pb.notes, workspace_pb.labels):
        documents.extend(make_public_capabilities_documents(ARObjectType.NOTE, note.id))

    # Documents for any embedded playbooks
    for playbook in workspace_pb.arPlaybooks:
        documents.extend(make_public_capabilities_documents(ARObjectType.PLAYBOOK, playbook.id))

    return documents


@defer.inlineCallbacks
def _check_should_init_capabilities_collection(kvstore, auth_header):
    capabilities_response = yield kvstore.async_kvstore_get_request(collection=AR_CAPABILITIES_COLLECTION,
                                                                    auth_header=auth_header,
                                                                    params={LIMIT: 1})
    if capabilities_response.code != http.OK:
        message = yield capabilities_response.text()
        LOGGER.error('Failed to check AR capabilities collection for entries with message=%s status_code=%d',
                     message, capabilities_response.code)
        defer.returnValue(False)

    entry = yield capabilities_response.json()
    if entry:
        LOGGER.debug('There is already a document in the capabilities table: %s', entry)
        defer.returnValue(False)

    defer.returnValue(True)


@defer.inlineCallbacks
def cleanup_deleted_roles(splunk, kvstore, permissions, auth_header):
    context = RequestContext(auth_header)
    current_role_names = yield _get_all_role_names(splunk, auth_header)
    roles_that_no_longer_exist = yield _get_roles_in_capabilities_table_other_than(auth_header, kvstore,
                                                                                   current_role_names)
    if roles_that_no_longer_exist:
        yield permissions.delete_roles_from_capabilities_table(context, roles_that_no_longer_exist)
        LOGGER.debug('Removed stale data for roles=%s', roles_that_no_longer_exist)
    else:
        LOGGER.debug("No roles have been deleted since last iteration roles=%s.", current_role_names)


@defer.inlineCallbacks
def _get_all_role_names(splunk, auth_header):
    get_all_roles_response = yield splunk.async_get_viewable_roles(auth_header)
    if get_all_roles_response.code != http.OK:
        message = yield get_all_roles_response.text()
        raise SpacebridgeError(
            'Failed to query all splunk roles message={} status_code={}'.format(message, get_all_roles_response.code))
    all_roles_json = yield get_all_roles_response.json()
    defer.returnValue({role[NAME] for role in all_roles_json[ENTRY]})


@defer.inlineCallbacks
def _get_roles_in_capabilities_table_other_than(auth_header, kvstore, existing_roles):
    roles_to_exclude = existing_roles | {AR_PUBLIC_READ_ROLE, AR_PUBLIC_WRITE_ROLE}
    params = {
        QUERY: json.dumps({
            AND_OPERATOR: [{ROLE: {NOT_EQUAL: role}} for role in roles_to_exclude]
        })
    }
    get_roles_response = yield kvstore.async_kvstore_get_request(
        collection=AR_CAPABILITIES_COLLECTION, auth_header=auth_header, params=params)
    if get_roles_response.code != http.OK:
        message = yield get_roles_response.text()
        raise SpacebridgeError(
            'Failed to lookup roles from the AR capabilities collection message={} status_code={}'.format(
                message, get_roles_response.code))
    roles_json = yield get_roles_response.json()
    defer.returnValue({doc[ROLE] for doc in roles_json})


def _wait_for_kvstore_to_start(uri, session_key, timeout_seconds):
    LOGGER.debug('Checking KV store availability')
    sleep_interval_seconds = 2
    kvstore = StateStore()
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if kvstore.is_available(host_base_uri=uri, session_key=session_key):
            return
        LOGGER.debug('KV store not yet available')
        time.sleep(sleep_interval_seconds)


if __name__ == '__main__':
    ARModularInput().execute()
