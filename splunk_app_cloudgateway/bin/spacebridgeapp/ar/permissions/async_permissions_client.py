"""
(C) 2019 Splunk Inc. All rights reserved.

Module providing client for making asynchronous requests to resolve AR permissions using Twisted
"""
from __future__ import print_function

from collections import defaultdict, deque
import enum
import json

from spacebridgeapp.ar.ar_util import wait_for_all
from spacebridgeapp.ar.data.data_class_mixin import DataClassMixin
from spacebridgeapp.ar.storage.queries import get_query_matching_keys, get_query_matching_field
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError, SpacebridgeARPermissionError
from spacebridgeapp.util import async_lru_cache
from spacebridgeapp.util.constants import (
    SPACEBRIDGE_APP_NAME, OR_OPERATOR, GREATER_THAN_OR_EQUAL_TO_OPERATOR, ENTRY, CONTENT, QUERY, AND_OPERATOR, LIMIT,
    NAME, KEY, NOT_EQUAL)
from twisted.internet import defer
from twisted.web import http

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + '_async_ar_permissions_client.log', 'async_ar_permissions_client')
AR_CAPABILITIES_COLLECTION = 'ar_capabilities'
AR_PUBLIC_READ_ROLE = '+++__AR_DEFAULT_PUBLIC_READ_ROLE__+++'
AR_PUBLIC_WRITE_ROLE = '+++__AR_DEFAULT_PUBLIC_WRITE_ROLE__+++'
OBJECT_TYPE = 'object_type'
OBJECT_ID = 'object_id'
ROLE = 'role'
ACCESS_LEVEL = 'access_level'
ROLES = 'roles'
IMPORTED_ROLES = 'imported_roles'
CAPABILITIES = 'capabilities'

LEVEL_READ = 1
LEVEL_WRITE = 2
LEVEL_MANAGE = 3

READ_SUFFIX = 'read'
WRITE_SUFFIX = 'write'
MANAGE_SUFFIX = 'manage'


class ARObjectType(enum.Enum):
    ASSET = 'asset'
    ASSET_GROUP = 'asset_group'
    BEACON = 'beacon'
    GEOFENCE = 'geofence'
    WORKSPACE = 'workspace'
    NOTE = 'note'
    PLAYBOOK = 'playbook'


class Capabilities(enum.Enum):
    ASSET_READ = (LEVEL_READ, ARObjectType.ASSET, 'asset_read')
    ASSET_WRITE = (LEVEL_WRITE, ARObjectType.ASSET, 'asset_write')
    ASSET_MANAGE = (LEVEL_MANAGE, ARObjectType.ASSET, 'asset_manage')

    ASSET_GROUP_READ = (LEVEL_READ, ARObjectType.ASSET_GROUP, 'asset_group_read')
    ASSET_GROUP_WRITE = (LEVEL_WRITE, ARObjectType.ASSET_GROUP, 'asset_group_write')
    ASSET_GROUP_MANAGE = (LEVEL_MANAGE, ARObjectType.ASSET_GROUP, 'asset_group_manage')

    BEACON_READ = (LEVEL_READ, ARObjectType.BEACON, 'beacon_read')
    BEACON_WRITE = (LEVEL_WRITE, ARObjectType.BEACON, 'beacon_write')
    BEACON_MANAGE = (LEVEL_MANAGE, ARObjectType.BEACON, 'beacon_manage')

    GEOFENCE_READ = (LEVEL_READ, ARObjectType.GEOFENCE, 'geofence_read')
    GEOFENCE_WRITE = (LEVEL_WRITE, ARObjectType.GEOFENCE, 'geofence_write')
    GEOFENCE_MANAGE = (LEVEL_MANAGE, ARObjectType.GEOFENCE, 'geofence_manage')

    WORKSPACE_READ = (LEVEL_READ, ARObjectType.WORKSPACE, 'workspace_read')
    WORKSPACE_WRITE = (LEVEL_WRITE, ARObjectType.WORKSPACE, 'workspace_write')
    WORKSPACE_MANAGE = (LEVEL_MANAGE, ARObjectType.WORKSPACE, 'workspace_manage')

    NOTE_READ = (LEVEL_READ, ARObjectType.NOTE, 'note_read')
    NOTE_WRITE = (LEVEL_WRITE, ARObjectType.NOTE, 'note_write')
    NOTE_MANAGE = (LEVEL_MANAGE, ARObjectType.NOTE, 'note_manage')

    PLAYBOOK_READ = (LEVEL_READ, ARObjectType.PLAYBOOK, 'playbook_read')
    PLAYBOOK_WRITE = (LEVEL_WRITE, ARObjectType.PLAYBOOK, 'playbook_write')
    PLAYBOOK_MANAGE = (LEVEL_MANAGE, ARObjectType.PLAYBOOK, 'playbook_manage')

    # TODO: Once users are migrated to the new permissions model we should deprecate and remove this.
    AR_WRITE = (4, 'all', 'ar_write')

    @property
    def level(self):
        return self.value[0]

    @property
    def type(self):
        return self.value[1]

    @property
    def name(self):
        return self.value[2]

    def read_equivalent(self):
        return Capabilities.from_type_and_level(self.type, LEVEL_READ)

    def write_equivalent(self):
        return Capabilities.from_type_and_level(self.type, LEVEL_WRITE)

    def manage_equivalent(self):
        return Capabilities.from_type_and_level(self.type, LEVEL_MANAGE)

    @staticmethod
    def from_type_and_level(object_type, access_level):
        if access_level == LEVEL_READ:
            name_suffix = READ_SUFFIX
        elif access_level == LEVEL_WRITE:
            name_suffix = WRITE_SUFFIX
        elif access_level == LEVEL_MANAGE:
            name_suffix = MANAGE_SUFFIX
        else:
            raise ValueError('Invalid access level: {}'.format(access_level))

        return Capabilities((access_level, object_type, '{}_{}'.format(object_type.value, name_suffix)))

    @staticmethod
    def from_name(name):
        if name == 'ar_write':
            return Capabilities.AR_WRITE

        last_underscore = name.rfind('_')
        if last_underscore < 0:
            return None

        try:
            object_type = ARObjectType(name[:last_underscore])
        except ValueError:
            return None

        level_suffix = name[last_underscore + 1:]
        if level_suffix == READ_SUFFIX:
            access_level = 1
        elif level_suffix == WRITE_SUFFIX:
            access_level = 2
        elif level_suffix == MANAGE_SUFFIX:
            access_level = 3
        else:
            return None

        return Capabilities.from_type_and_level(object_type, access_level)

    @staticmethod
    def read_capabilities():
        return [c for c in Capabilities if c.level == LEVEL_READ]

    @staticmethod
    def write_capabilities():
        return [c for c in Capabilities if c.level == LEVEL_WRITE]

    @staticmethod
    def granted_by(capability):
        if capability == Capabilities.AR_WRITE:
            return [c for c in Capabilities]
        return [c for c in Capabilities if c.type == capability.type and c.level <= capability.level]

    @staticmethod
    def granting(capability):
        capabilities = [c for c in Capabilities if c.type == capability.type and c.level >= capability.level]
        capabilities.append(Capabilities.AR_WRITE)
        return capabilities

    def __lt__(self, other):
        return isinstance(other, Capabilities) and self.name < other.name

    def __repr__(self):
        return 'Capabilities.{}'.format(self.name.upper())


class AccessQuantity(enum.Enum):
    NONE = 1
    SOME = 2
    ALL = 3


class Access(DataClassMixin):

    def __init__(self, quantity, object_ids=None):
        self._quantity = quantity
        self._object_ids = object_ids or []

    @property
    def quantity(self):
        return self._quantity

    @property
    def ids(self):
        return set(self._object_ids)

    @staticmethod
    def all():
        return Access(quantity=AccessQuantity.ALL)

    def __eq__(self, other):
        return type(self) == type(other) and self.quantity == other.quantity and self.ids == other.ids

    def __hash__(self):
        return hash((self.quantity, frozenset(self._object_ids)))

    def __repr__(self):
        return 'Access(quantity={}, object_ids={})'.format(self.quantity, list(self.ids))


class ObjectCapability(DataClassMixin):

    def __init__(self, object_id, object_type, access_level):
        self.object_id = object_id
        self.object_type = object_type
        self.access_level = access_level

    def to_kvstore_capabilities_entry(self, role):
        """Creates a KV store document for the AR capabilities table based on the given role and capability."""
        return {
            KEY: make_ar_capabilities_entry_key(role, self.object_type, self.object_id),
            ACCESS_LEVEL: self.access_level,
            OBJECT_TYPE: self.object_type.value,
            OBJECT_ID: self.object_id,
            ROLE: role
        }

    @staticmethod
    def from_kvstore_document(doc):
        return ObjectCapability(
            object_id=doc[OBJECT_ID],
            object_type=ARObjectType(doc[OBJECT_TYPE]),
            access_level=doc[ACCESS_LEVEL]
        )

    def __hash__(self):
        return hash((self.object_id, self.object_type, self.access_level))

    def __repr__(self):
        return 'ObjectCapability(object_id={}, object_type={}, access_level={})'.format(
            self.object_id, self.object_type, self.access_level)

    @staticmethod
    def from_dict(d):
        """A convenience for organizing an object capability from a REST request payload."""
        access_level = d['accessLevel']
        if access_level not in {LEVEL_READ, LEVEL_WRITE}:
            raise ValueError('Invalid access level: {}'.format(access_level))
        return ObjectCapability(
            object_id=d['id'],
            object_type=ARObjectType(d['type']),
            access_level=access_level
        )


class AsyncArPermissionsClient(object):
    """Client for validating AR permissions.

    NOTE: Subsequent calls to check_permissions and check_multiple_permissions for the same request_context will be fast
          because we cache the results of current context lookups. Subsequent calls to get_accessible_objects and
          get_object_permission will be faster than the first call since the user role lookup is cached, but each check
          will still require at least one call to KV store.
    """

    def __init__(self, splunk_client, kvstore_client):
        """
        :param splunk_client: an async_splunk_client.AsyncSplunkClient
        :param kvstore_client: an async_kvstore_client.AsyncKvStoreClient
        """
        self._splunk_client = splunk_client
        self._kvstore_client = kvstore_client

    @defer.inlineCallbacks
    def get_accessible_objects(self, request_context, *capabilities):
        """
        Retrieves a set of AR object IDs that the user has access to for each of the given capabilities.

        :param request_context: The RequestContext of the given request
        :param capabilities: The Capabilities to check
        :return: An Access for each of the given capabilities.
        """
        list_accessible_objects_query = yield self._build_list_accessible_objects_query(request_context, capabilities)
        if not list_accessible_objects_query:
            # The generated query is None so we know that the user has access to every object for each of the listed
            # capabilities.
            all_access = Access.all()
            defer.returnValue(all_access if len(capabilities) == 1 else [all_access for _ in capabilities])

        LOGGER.debug('Listing accessible objects for user=%s with query=%s', request_context.current_user,
                     list_accessible_objects_query[QUERY])
        list_accessible_objects_response = yield self._kvstore_client.async_kvstore_get_request(
            auth_header=request_context.auth_header, collection=AR_CAPABILITIES_COLLECTION,
            params=list_accessible_objects_query)
        if list_accessible_objects_response.code != http.OK:
            message = yield list_accessible_objects_response.text()
            raise SpacebridgeApiRequestError(message=message, status_code=list_accessible_objects_response.code)
        accessible_objects_json = yield list_accessible_objects_response.json()

        # Map accessible IDs to their type then level:
        # workspace -> read -> [a, b, ...]
        #           -> write -> [a, b, ...]
        ids_by_type = defaultdict(lambda: defaultdict(set))
        for accessible_object in accessible_objects_json:
            object_type = accessible_object[OBJECT_TYPE]
            access_level = accessible_object[ACCESS_LEVEL]
            ids_by_type[object_type][access_level].add(accessible_object[OBJECT_ID])

        accesses = []
        for capability in capabilities:
            has_manage_equivalent = yield self.check_permission(request_context, capability.manage_equivalent(),
                                                                raise_on_missing=False)
            if has_manage_equivalent:
                accesses.append(Access.all())
                continue

            accessible_ids = set()
            for level, ids in ids_by_type[capability.type.value].items():
                if capability.level <= level:
                    accessible_ids |= ids
            if accessible_ids:
                accesses.append(Access(quantity=AccessQuantity.SOME, object_ids=accessible_ids))
            else:
                accesses.append(Access(quantity=AccessQuantity.NONE))

        defer.returnValue(accesses[0] if len(accesses) == 1 else accesses)

    @defer.inlineCallbacks
    def _build_list_accessible_objects_query(self, request_context, capabilities):
        roles = yield self._get_assigned_roles(request_context)
        object_type_filters = []
        for capability in capabilities:
            has_general_read, has_general_write, has_general_manage = yield self.check_multiple_permissions(
                request_context, [
                    capability.read_equivalent(),
                    capability.write_equivalent(),
                    capability.manage_equivalent()
                ], raise_on_missing=False)
            if has_general_manage:
                # This user has access to all objects of the given type so there's no point in fetching specific IDs.
                continue

            roles_to_consider = set(roles)
            if has_general_write:
                roles_to_consider.add(AR_PUBLIC_WRITE_ROLE)
            if has_general_read:
                roles_to_consider.add(AR_PUBLIC_READ_ROLE)
            object_type_filters.append({
                AND_OPERATOR: [
                    {OR_OPERATOR: [{ROLE: role} for role in roles_to_consider]},
                    {OBJECT_TYPE: capability.type.value},
                    {ACCESS_LEVEL: {GREATER_THAN_OR_EQUAL_TO_OPERATOR: capability.level}}
                ]
            })

        # The user has the manage equivalent for all the given capabilities. We shouldn't bother querying for specific
        # IDs they have access to at this point.
        if not object_type_filters:
            defer.returnValue(None)

        query = {OR_OPERATOR: object_type_filters}
        defer.returnValue({QUERY: json.dumps(query)})

    @defer.inlineCallbacks
    def check_object_permission(self, request_context, capability, object_id, raise_on_missing=True):
        """
        Checks whether a user has access to a specific AR object.

        :param request_context: The RequestContext of the request
        :param capability: The Capabilities enum to check access for
        :param object_id: The AR object ID to lookup
        :param raise_on_missing: (optional) Whether to raise an exception if the user does not have access to the given
                                 object.
        :return: Whether or not the user has access to the given capability for the given object.
        """
        if capability.level not in {LEVEL_READ, LEVEL_WRITE}:
            raise TypeError('Must use a read or write capability. Found {} instead.'.format(capability))

        has_general_manage = yield self.check_permission(
            request_context, capability.manage_equivalent(), raise_on_missing=False)
        if has_general_manage:
            # General manage capabilities grant access to all objects of a given type.
            defer.returnValue(True)

        object_permission_query = yield self._build_object_permission_query(request_context, capability, object_id)
        LOGGER.debug('Checking whether username=%s has capability=%s for object_id=%s with query=%s',
                     request_context.current_user, capability.name, object_id,
                     json.dumps(object_permission_query[QUERY], indent=2, sort_keys=True))
        object_permission_response = yield self._kvstore_client.async_kvstore_get_request(
            auth_header=request_context.auth_header, collection=AR_CAPABILITIES_COLLECTION,
            params=object_permission_query)
        if object_permission_response.code != http.OK:
            message = yield object_permission_response.text()
            raise SpacebridgeApiRequestError(message=message, status_code=object_permission_response.code)
        object_permission_json = yield object_permission_response.json()
        if object_permission_json:
            defer.returnValue(True)

        if raise_on_missing:
            raise SpacebridgeARPermissionError(
                'User username={} does not have {} access to object_type={} object_id={}'.format(
                    request_context.current_user,
                    'read' if capability.level == LEVEL_READ else 'write', capability.type, object_id))
        defer.returnValue(False)

    @defer.inlineCallbacks
    def _build_object_permission_query(self, request_context, capability, object_id):
        user_roles = yield self._get_assigned_roles(request_context)
        has_general_read, has_general_write = yield self.check_multiple_permissions(
            request_context, [capability.read_equivalent(), capability.write_equivalent()], raise_on_missing=False)
        if has_general_write:
            user_roles.add(AR_PUBLIC_WRITE_ROLE)
        if has_general_read:
            user_roles.add(AR_PUBLIC_READ_ROLE)
        query = {
            QUERY: json.dumps({
                AND_OPERATOR: [
                    {OBJECT_ID: object_id},
                    {OBJECT_TYPE: capability.type.value},
                    {ACCESS_LEVEL: {GREATER_THAN_OR_EQUAL_TO_OPERATOR: capability.level}},
                    {OR_OPERATOR: [{ROLE: role} for role in user_roles]}
                ]
            }),
            LIMIT: 1,
        }
        defer.returnValue(query)

    @defer.inlineCallbacks
    def check_permission(self, request_context, capability, message=None, raise_on_missing=True):
        """
        Checks whether a user has the given capability on a class of AR objects.

        :param request_context: A RequestContext for the given request.
        :param capability: The capability the user must have either explicitly or implicitly to pass this check.
        :param message: The message to attach to the raised exception upon failure.
        :param raise_on_missing: If true, this will raise a SpacebridgeARPermissionError if the user does not have the
                                 given capability or one implicitly granting it.
        """
        result = yield self.check_multiple_permissions(request_context, [capability], message=message,
                                                       raise_on_missing=raise_on_missing)
        defer.returnValue(result[0])

    @defer.inlineCallbacks
    def check_multiple_permissions(self, request_context, capabilities, message=None, raise_on_missing=True):
        """
        Checks whether a user has any of the given permissions.

        This returns a list of booleans corresponding to which permissions the user has. If the user does not have
        any of the given permissions, a spacebridge_exceptions.SpaceBridgeARPermissionException is raised.

        :param request_context: A RequestContext for the given request.
        :param capabilities: a list of capabilities to check for.
        :param message: The message to attach to the raised exception if the user has none of the given permissions.
        :param raise_on_missing: bool indicating whether to raise an exception if the user has none of the
                                 requested capabilities
        :return: A list of booleans indicating which permissions the user has.
        """
        user_capabilities = yield self._get_user_splunk_capabilities(request_context)
        validation_results = []
        for capability in capabilities:
            sufficient_capabilities = [c.name for c in Capabilities.granting(capability)]
            validation_results.append(True if user_capabilities.intersection(sufficient_capabilities) else False)

        if raise_on_missing and not any(validation_results):
            raise SpacebridgeARPermissionError(message=message or 'Forbidden')

        defer.returnValue(validation_results)

    @defer.inlineCallbacks
    def get_user_capabilities(self, request_context):
        """
        Returns a tuple representing the user's general splunk level capabilities and AR object capabilities.

        The tuple will contain:
        * A set of general splunk level capability names the user has
        * A dict of Capability -> Access objects for each of the read and write level AR capabilities
        """
        general_capabilities = yield self._get_user_splunk_capabilities(request_context)

        capabilities_to_check = Capabilities.read_capabilities() + Capabilities.write_capabilities()
        accesses = yield self.get_accessible_objects(request_context, *capabilities_to_check)
        capabilities_to_access_map = {capability: access for capability, access in zip(capabilities_to_check, accesses)}

        defer.returnValue((general_capabilities, capabilities_to_access_map))

    @defer.inlineCallbacks
    def get_capabilities_granted_by_role(self, request_context, role):
        """Returns the same tuple described in get_user_capabilities but for the specific role instead of the user."""
        general_capabilities, object_access_by_capability = yield wait_for_all([
            self._get_general_capabilities_for_role(request_context, role),
            self.get_object_capabilities_granted_by_role(request_context, role)
        ], raise_on_first_exception=True)
        defer.returnValue((general_capabilities, object_access_by_capability))

    @defer.inlineCallbacks
    def get_object_capabilities_granted_by_role(self, request_context, role):
        capabilities_documents = yield self._get_documents_for_roles(request_context, [role])
        accessible_ids_by_capability = defaultdict(set)
        for doc in capabilities_documents:
            capability = Capabilities.from_type_and_level(ARObjectType(doc[OBJECT_TYPE]), doc[ACCESS_LEVEL])
            accessible_ids_by_capability[capability].add(doc[OBJECT_ID])

        access_by_capability = {}
        for capability, accessible_ids in accessible_ids_by_capability.items():
            access = (Access(quantity=AccessQuantity.SOME, object_ids=accessible_ids)
                      if accessible_ids else
                      Access(quantity=AccessQuantity.NONE))
            access_by_capability[capability] = access

        defer.returnValue(access_by_capability)

    @defer.inlineCallbacks
    def _get_documents_for_roles(self, request_context, roles):
        # If this role already has access to all objects of a given type we don't want those objects in the result set.
        object_types_filter = None
        query = {ROLE: roles[0]} if len(roles) == 1 else {OR_OPERATOR: [{ROLE: role} for role in roles]}
        if object_types_filter:
            query = {AND_OPERATOR: [query, object_types_filter]}

        # Retrieve all capabilities documents that reference the given role
        capabilities_tied_to_role_response = yield self._kvstore_client.async_kvstore_get_request(
            collection=AR_CAPABILITIES_COLLECTION, auth_header=request_context.auth_header,
            params={QUERY: json.dumps(query)})
        if capabilities_tied_to_role_response.code != http.OK:
            message = yield capabilities_tied_to_role_response.text()
            raise SpacebridgeApiRequestError(
                'Unable to fetch AR capabilities for roles={} message="{}" status_code={}'.format(
                    roles, message, capabilities_tied_to_role_response.code),
                status_code=capabilities_tied_to_role_response.code)
        capabilities_documents = yield capabilities_tied_to_role_response.json()
        defer.returnValue(capabilities_documents)

    @defer.inlineCallbacks
    def _user_can_edit_object_capabilities(self, request_context):
        capabilities = yield self._get_user_splunk_capabilities(request_context)
        defer.returnValue('ar_edit_roles' in capabilities)

    @defer.inlineCallbacks
    def _user_can_edit_roles(self, request_context):
        capabilities = yield self._get_user_splunk_capabilities(request_context)
        defer.returnValue('edit_roles' in capabilities)

    @defer.inlineCallbacks
    def _get_general_capabilities_for_role(self, request_context, role):
        role_json = yield self._get_role(request_context, role)
        capabilities = role_json.get(CONTENT, {}).get(CAPABILITIES, [])
        defer.returnValue(set(capabilities))

    @defer.inlineCallbacks
    def _get_user_splunk_capabilities(self, request_context):
        """Returns a set containing all of the user's Splunk core capabilities."""
        current_context_json = yield self._get_current_context(request_context)
        defer.returnValue(set(current_context_json[CONTENT]['capabilities']))

    @defer.inlineCallbacks
    def _get_role(self, request_context, role_name):
        role_response = yield self._splunk_client.async_get_role(request_context.auth_header, role_name)
        if role_response.code != http.OK:
            message = yield role_response.text()
            raise SpacebridgeApiRequestError(
                'Failed to lookup role="{}" message="{}" status_code={}'.format(role_name, message, role_response.code),
                status_code=role_response.code)
        role_json = yield role_response.json()
        defer.returnValue(role_json[ENTRY][0])

    @defer.inlineCallbacks
    def _get_assigned_roles(self, request_context):
        direct_roles = yield self._get_user_direct_roles(request_context)
        roles_json = yield self._get_roles_json(request_context)
        child_to_parent_roles = _get_role_field_by_name(roles_json, IMPORTED_ROLES)
        user_roles = set(direct_roles)
        q = deque(direct_roles)
        while q:
            child_role = q.pop()
            for parent_role in child_to_parent_roles.get(child_role, []):
                if parent_role not in user_roles:
                    user_roles.add(parent_role)
                    q.appendleft(parent_role)
        defer.returnValue(user_roles)

    @defer.inlineCallbacks
    def _get_user_direct_roles(self, request_context):
        current_context_json = yield self._get_current_context(request_context)
        defer.returnValue(current_context_json[CONTENT][ROLES])

    @async_lru_cache.memoize
    @defer.inlineCallbacks
    def _get_roles_json(self, request_context):
        viewable_roles_response = yield self._splunk_client.async_get_viewable_roles(request_context.auth_header)
        if viewable_roles_response.code != http.OK:
            message = yield viewable_roles_response.text()
            raise SpacebridgeApiRequestError(message=message, status_code=viewable_roles_response.code)
        viewable_roles_json = yield viewable_roles_response.json()
        defer.returnValue(viewable_roles_json)

    @async_lru_cache.memoize
    @defer.inlineCallbacks
    def _get_current_context(self, request_context):
        current_context_response = yield self._splunk_client.async_get_current_context(request_context.auth_header)
        if current_context_response.code != http.OK:
            response_text = yield current_context_response.text()
            raise SpacebridgeApiRequestError(message=response_text, status_code=current_context_response.code)
        current_context_json = yield current_context_response.json()
        defer.returnValue(current_context_json[ENTRY][0])

    @defer.inlineCallbacks
    def create_role(self, request_context, name, parent_roles=None, general_capabilities=None,
                    object_capabilities=None):
        """
        Creates a new Splunk role with the given settings.

        :param request_context: The RequestContext for the request.
        :param name: The name of the role to create.
        :param parent_roles: A list of role names the new role should inherit from.
        :param general_capabilities: A list of capability names this role should possess.
        :param object_capabilities: A list of ObjectCapability that this role should possess.
        :return: The name of the created role. This may differ from "name" since Splunk formats role names. Thus far I
                 have only seen Splunk make names lowercase but there may be other formatting so do not assume calling
                 name.lower() will result in the same name returned from here.
        """
        user_can_edit_roles = yield self._user_can_edit_roles(request_context)
        if not user_can_edit_roles:
            raise SpacebridgeARPermissionError('User must have edit_roles or ar_edit_roles to update AR roles.')

        create_role_response = yield self._splunk_client.async_create_role(
            auth_header=request_context.auth_header, name=name, imported_roles=parent_roles,
            capabilities=general_capabilities)
        if create_role_response.code not in {http.OK, http.CREATED}:
            message = yield create_role_response.text()
            raise SpacebridgeApiRequestError(
                'Failed to create role="{}" message="{}" status_code={}'.format(name, message,
                                                                                create_role_response.code),
                status_code=create_role_response.code)
        created_role_json = yield create_role_response.json()
        name = created_role_json[ENTRY][0][NAME]
        if object_capabilities:
            yield self._add_object_capabilities_to_role(request_context, name, object_capabilities)
        defer.returnValue(name)

    @defer.inlineCallbacks
    def update_role(self, request_context, name, parent_roles=None, general_capabilities=None,
                    object_capabilities=None):
        """
        Updates an existing role name with the given parameters. Repeated fields overwrite existing ones *not* append.

        :param request_context: The RequestContext for the request.
        :param name: The name of the role to update.
        :param parent_roles: A list of role names the role should inherit from.
        :param general_capabilities: A list of capability names this role should possess.
        :param object_capabilities: A list of ObjectCapability that this role should possess.
        """
        user_can_edit_roles = yield self._user_can_edit_roles(request_context)
        user_can_edit_object_capabilities = yield self._user_can_edit_object_capabilities(request_context)
        if not user_can_edit_roles and not user_can_edit_object_capabilities:
            raise SpacebridgeARPermissionError('User must have edit_roles or ar_edit_roles to update AR roles.')

        if user_can_edit_roles:
            update_role_response = yield self._splunk_client.async_update_role(
                auth_header=request_context.auth_header, name=name, imported_roles=parent_roles,
                capabilities=general_capabilities)
            if update_role_response.code != http.OK:
                message = yield update_role_response.text()
                raise SpacebridgeApiRequestError(
                    'Failed to update role="{}" message="{}" status_code={}'.format(name, message,
                                                                                    update_role_response.code),
                    status_code=update_role_response.code)

        if object_capabilities is not None and user_can_edit_object_capabilities:
            existing_access_by_capability = yield self.get_object_capabilities_granted_by_role(request_context, name)
            existing_object_capabilities = _convert_to_object_capabilities(existing_access_by_capability)
            updated_object_capabilities = set(object_capabilities)

            to_remove = existing_object_capabilities - updated_object_capabilities
            to_add = updated_object_capabilities - existing_object_capabilities
            yield defer.DeferredList([
                self._remove_object_capabilities_from_role(request_context, name, to_remove),
                self._add_object_capabilities_to_role(request_context, name, to_add)
            ])

        defer.returnValue(name)

    @defer.inlineCallbacks
    def _add_object_capabilities_to_role(self, request_context, role_name, capabilities_to_add):
        if not capabilities_to_add:
            return

        # Write the given object capabilities to the AR capabilities table and associate them with the given role
        effected_ids = yield self._kvstore_client.async_batch_save_request(
            collection=AR_CAPABILITIES_COLLECTION,
            auth_header=request_context.auth_header,
            entries=[oc.to_kvstore_capabilities_entry(role_name) for oc in capabilities_to_add])
        LOGGER.debug('Wrote capabilities=%s for role="%s"', effected_ids, role_name)

        # Remove the effected objects from either the read or write public pool.
        keys_to_delete = []
        for oc in capabilities_to_add:
            if oc.access_level == LEVEL_READ:
                keys_to_delete.append(make_ar_capabilities_entry_key(AR_PUBLIC_READ_ROLE, oc.object_type, oc.object_id))
            keys_to_delete.append(make_ar_capabilities_entry_key(AR_PUBLIC_WRITE_ROLE, oc.object_type, oc.object_id))
        delete_response = yield self._kvstore_client.async_kvstore_delete_request(
            collection=AR_CAPABILITIES_COLLECTION, auth_header=request_context.auth_header,
            params={QUERY: get_query_matching_keys(keys_to_delete)})
        if delete_response.code != http.OK:
            message = yield delete_response.text()
            raise SpacebridgeApiRequestError(
                'Failed to remove the following keys from the AR capabilities table for role="{}" keys={} message={} '
                'status_code={}'.format(role_name, keys_to_delete, message, delete_response.code),
                status_code=delete_response.code)

    @defer.inlineCallbacks
    def _remove_object_capabilities_from_role(self, request_context, role_name, capabilities_to_remove):
        if not capabilities_to_remove:
            return

        # Delete all of the given capabilities from the AR capabilities table
        params = {
            QUERY: get_query_matching_keys([
                make_ar_capabilities_entry_key(role_name, capability.object_type, capability.object_id)
                for capability in capabilities_to_remove
            ])
        }
        LOGGER.debug('Removing objects from role=%s with query=%s', role_name, params)
        delete_response = yield self._kvstore_client.async_kvstore_delete_request(
            collection=AR_CAPABILITIES_COLLECTION, auth_header=request_context.auth_header, params=params)
        if delete_response.code != http.OK:
            message = yield delete_response.text()
            raise SpacebridgeApiRequestError(
                'Failed to remove object capabilities for role="{}" message="{}" status_code={}'.format(
                    role_name, message, delete_response.code),
                status_code=delete_response.code)

        # Now add back any of the effected object IDs to the public read/write pools if there are no other roles
        # that reference them.
        yield self._restore_object_ids_to_public_pool(request_context, capabilities_to_remove)

    @defer.inlineCallbacks
    def _restore_object_ids_to_public_pool(self, request_context, object_capabilities):
        capabilities_for_ids = yield self._get_documents_for_object_ids(request_context,
                                                                        [oc.object_id for oc in object_capabilities])

        # id -> (should add to public read pool, should add to public write pool)
        object_id_access = defaultdict(lambda: [True, True])
        for capability in capabilities_for_ids:
            object_id = capability[OBJECT_ID]
            if capability[ACCESS_LEVEL] == LEVEL_READ:
                object_id_access[object_id] = [False, False]
            else:
                object_id_access[object_id][1] = False

        documents_to_write = []
        for oc in object_capabilities:
            should_be_public_read, should_be_public_write = object_id_access[oc.object_id]
            if should_be_public_read:
                documents_to_write.append(make_public_read_capability_document(oc.object_type, oc.object_id))
            if should_be_public_write:
                documents_to_write.append(make_public_write_capability_document(oc.object_type, oc.object_id))

        if documents_to_write:
            updated_ids = yield self._kvstore_client.async_batch_save_request(
                collection=AR_CAPABILITIES_COLLECTION, auth_header=request_context.auth_header,
                entries=documents_to_write)
            LOGGER.debug('Added back the following AR objects to the public access pool object_ids=%s', updated_ids)

    @defer.inlineCallbacks
    def _get_documents_for_object_ids(self, request_context, object_ids):
        if not object_ids:
            defer.returnValue([])

        capabilities_for_ids = yield self._kvstore_client.async_kvstore_get_request(
            collection=AR_CAPABILITIES_COLLECTION, auth_header=request_context.auth_header,
            params={
                QUERY: json.dumps({
                    OR_OPERATOR: [{OBJECT_ID: object_id} for object_id in object_ids]
                })
            })
        if capabilities_for_ids.code != http.OK:
            message = yield capabilities_for_ids.text()
            raise SpacebridgeApiRequestError('Failed to lookup object_ids={} to add back to the public access pool '
                                             'message="{}" status_code={}'.format(object_ids, message,
                                                                                  capabilities_for_ids.code),
                                             status_code=capabilities_for_ids.code)
        capabilities_json = yield capabilities_for_ids.json()
        defer.returnValue(capabilities_json)

    @defer.inlineCallbacks
    def register_objects(self, request_context, object_type, object_ids, check_if_objects_exist=False):
        """
        Adds AR objects to the capabilities table so they are visible to users with X_read capabilities.

        :param request_context: The RequestContext of the request.
        :param object_type: The ARObjectType of the objects being initialized.
        :param object_ids: A list of object IDs to initialize.
        :param check_if_objects_exist: (optional) If True, this will only write documents for objects that have not
                                       already been initialized.
        """
        if not object_ids:
            return

        if check_if_objects_exist:
            capability_documents_response = yield self._kvstore_client.async_kvstore_get_request(
                collection=AR_CAPABILITIES_COLLECTION, auth_header=request_context.auth_header,
                params={QUERY: get_query_matching_field(OBJECT_ID, object_ids)})
            if capability_documents_response.code != http.OK:
                message = yield capability_documents_response.text()
                raise SpacebridgeApiRequestError(
                    'Failed to check whether object_ids={} were already configured for permissions. message={} '
                    'status_code={}'.format(object_ids, message, capability_documents_response.code),
                    status_code=capability_documents_response.code)
            capability_documents = yield capability_documents_response.json()
            already_configured_ids = {doc[OBJECT_ID] for doc in capability_documents}
            object_ids = [object_id for object_id in object_ids if object_id not in already_configured_ids]

        entries = []
        for object_id in object_ids:
            entries.extend(make_public_capabilities_documents(object_type, object_id))
        keys = yield self._kvstore_client.async_batch_save_request(
            collection=AR_CAPABILITIES_COLLECTION, auth_header=request_context.auth_header, entries=entries)
        LOGGER.debug('Initialized new permissions for object_ids=%s', keys)

    @defer.inlineCallbacks
    def delete_objects(self, request_context, object_ids):
        """
        Removes the given object IDs from the AR capabilities table.

        :param request_context: The RequestContext of the request.
        :param object_ids: The object IDs to remove.
        """
        if not object_ids:
            return

        delete_response = yield self._kvstore_client.async_kvstore_delete_request(
            collection=AR_CAPABILITIES_COLLECTION, auth_header=request_context.auth_header,
            params={QUERY: get_query_matching_field(OBJECT_ID, object_ids)})
        if delete_response.code != http.OK:
            message = yield delete_response.text()
            raise SpacebridgeApiRequestError(
                'Failed to remove capabilities documents for objects={} message={} status_code={}'.format(
                    object_ids, message, delete_response.code), status_code=delete_response.code)
        LOGGER.debug('Removed object_ids=%s from the capabilities table.', object_ids)

    @defer.inlineCallbacks
    def delete_role(self, request_context, role_name):
        """
        Removes the given role from Splunk and cleans up any AR KV store documents associated with that entry.

        If any objects associated with role_name are no longer associated with any role, they will be re-entered into
        the public pool of objects.

        :param request_context: The RequestContext for the request.
        :param role_name: The name of the role to delete.
        """
        user_can_edit_roles = yield self._user_can_edit_roles(request_context)
        if not user_can_edit_roles:
            raise SpacebridgeARPermissionError('User must have edit_roles or ar_edit_roles to update AR roles.')

        delete_role_from_splunk_response = yield self._splunk_client.async_delete_role(request_context.auth_header,
                                                                                       role_name)
        if delete_role_from_splunk_response.code != http.OK:
            message = yield delete_role_from_splunk_response.text()
            raise SpacebridgeApiRequestError(
                'Failed to delete role={} message={} status_code={}'.format(
                    role_name, message, delete_role_from_splunk_response.code),
                status_code=delete_role_from_splunk_response.code)

        yield self.delete_roles_from_capabilities_table(request_context, [role_name])

    @defer.inlineCallbacks
    def delete_roles_from_capabilities_table(self, request_context, role_names):
        if not role_names:
            return

        # Lookup which objects are referenced by the roles we're about to delete so we can add objects back to the
        # public pool if possible later on.
        documents_for_roles = yield self._get_documents_for_roles(request_context, role_names)
        capabilities_from_roles = [ObjectCapability.from_kvstore_document(doc) for doc in documents_for_roles]

        # Remove all entries in the capabilities KV store collection that reference the roles we'd like to delete.
        delete_roles_query = {
            QUERY: json.dumps(
                ({OR_OPERATOR: [{ROLE: role} for role in role_names]}
                 if len(role_names) > 1 else
                 {ROLE: next(iter(role_names))})
            )
        }
        delete_role_from_kvstore = yield self._kvstore_client.async_kvstore_delete_request(
            collection=AR_CAPABILITIES_COLLECTION, auth_header=request_context.auth_header, params=delete_roles_query)
        if delete_role_from_kvstore.code != http.OK:
            message = yield delete_role_from_kvstore.text()
            raise SpacebridgeApiRequestError(
                'Failed to delete roles={} from kvstore message={} status_code={}'.format(
                    role_names, message, delete_role_from_kvstore.code), status_code=delete_role_from_kvstore.code)

        # See if there are any other roles that reference the same set of IDs we retrieved earlier, and if not, add
        # no longer referenced IDs back to the public pools.
        yield self._restore_object_ids_to_public_pool(request_context, capabilities_from_roles)


def make_ar_capabilities_entry_key(role, object_type, object_id):
    return '{}|{}|{}'.format(role, object_type.value, object_id)


def make_public_capabilities_documents(object_type, object_id):
    return [
        make_public_read_capability_document(object_type, object_id),
        make_public_write_capability_document(object_type, object_id)
    ]


def make_public_read_capability_document(object_type, object_id):
    return {
        KEY: make_ar_capabilities_entry_key(AR_PUBLIC_READ_ROLE, object_type, object_id),
        ACCESS_LEVEL: LEVEL_READ,
        OBJECT_TYPE: object_type.value,
        OBJECT_ID: object_id,
        ROLE: AR_PUBLIC_READ_ROLE
    }


def make_public_write_capability_document(object_type, object_id):
    return {
        KEY: make_ar_capabilities_entry_key(AR_PUBLIC_WRITE_ROLE, object_type, object_id),
        ACCESS_LEVEL: LEVEL_WRITE,
        OBJECT_TYPE: object_type.value,
        OBJECT_ID: object_id,
        ROLE: AR_PUBLIC_WRITE_ROLE
    }


def _get_role_field_by_name(roles_json, field_name):
    name_to_field_value = {}
    for role in roles_json[ENTRY]:
        name = role[NAME]
        field_value = role.get(CONTENT, {}).get(field_name, [])
        name_to_field_value[name] = set(field_value)
    return name_to_field_value


def _convert_to_object_capabilities(accesses_by_capability):
    object_capabilities_by_id = {}
    for capability in Capabilities.read_capabilities() + Capabilities.write_capabilities():
        if capability not in accesses_by_capability:
            continue

        access = accesses_by_capability[capability]
        if access.quantity == AccessQuantity.ALL:
            continue
        for object_id in access.ids:
            object_capabilities_by_id[object_id] = ObjectCapability(object_id=object_id,
                                                                    object_type=capability.type,
                                                                    access_level=capability.level)
    return set(object_capabilities_by_id.values())
