"""
(C) 2020 Splunk Inc. All rights reserved.

Handles REST requests for accessing and updating AR related permissions.
"""
import collections
import sys
import json

from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from spacebridgeapp.ar.permissions.async_permissions_client import (
    Access, AccessQuantity, Capabilities, ObjectCapability, LEVEL_READ, LEVEL_WRITE
)
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.logging.setup_logging import setup_logging
from spacebridgeapp.messages.request_context import RequestContext
from spacebridgeapp.rest import async_base_endpoint
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, QUERY, STATUS, PAYLOAD
from twisted.internet import defer
from twisted.web import http

LOGGER = setup_logging(logfile_name='{}_permissions_rest.log'.format(SPACEBRIDGE_APP_NAME),
                       logger_name='ar_permissions_rest')

ROLE = 'role'
CAPABILITIES = 'capabilities'
READ = 'read'
WRITE = 'write'
ALL_ACCESS = 'ALL'
IMPORTED_ROLES = 'importedRoles'
GENERAL_CAPABILITIES = 'generalCapabilities'
OBJECT_CAPABILITIES = 'objectCapabilities'


class Permissions(async_base_endpoint.AsyncBaseRestHandler):

    def __init__(self, *args, **kwargs):
        super(Permissions, self).__init__(*args, **kwargs)
        self._permissions = self.async_client_factory.ar_permissions_client()

    @defer.inlineCallbacks
    def async_get(self, request):
        """
        Serves role and capability information relative to the user by default or a specific role if one is specified.

        Query Parameters:
        * role: if specified, this will return which capability this particular role grants

        Example Response:
        {
            "read": {
                "asset": ["asset_1", "asset_2"],
                "workspace": ["workspace_1", "workspace_2", "workspace_3"],
                "geofence": "ALL"
            },
            "write": {
                "note": ["note_1", "note_2"],
                "playbook": ["playbook_1"]
            },
            general: ["workspace_write", "asset_manage", "note_manage", "beacon_view"],
        }

        If the user has access to all objects of a specific type, the value for the object type key in "read" or "write"
        will have the value "ALL" instead of an actual list.

        :param request: a dictionary representing the HTTP request
        """
        context = RequestContext.from_rest_request(request)
        query = request.get(QUERY, {})

        if ROLE in query:
            capabilities, accesses = yield self._permissions.get_capabilities_granted_by_role(context, query[ROLE])
        else:
            capabilities, accesses = yield self._permissions.get_user_capabilities(context)

        read, write = collections.defaultdict(set), collections.defaultdict(set)
        for capability in Capabilities.read_capabilities() + Capabilities.write_capabilities():
            access = accesses.get(capability, Access(quantity=AccessQuantity.NONE))
            object_type = capability.type.value
            if access.quantity == AccessQuantity.ALL:
                read[object_type] = ALL_ACCESS
                write[object_type] = ALL_ACCESS
            elif capability.level == LEVEL_READ:
                read[object_type] |= access.ids
            elif capability.level == LEVEL_WRITE:
                read[object_type] |= access.ids
                write[object_type] |= access.ids

        for object_type in read:
            read[object_type] = list(read[object_type]) if isinstance(read[object_type], set) else read[object_type]
        for object_type in write:
            write[object_type] = list(write[object_type]) if isinstance(write[object_type], set) else write[object_type]

        defer.returnValue({
            STATUS: http.OK,
            PAYLOAD: {
                CAPABILITIES: sorted(capabilities),
                READ: dict(read),
                WRITE: dict(write)
            }
        })

    @defer.inlineCallbacks
    def async_post(self, request):
        role_name = yield self._create_or_update_role(request, self._permissions.create_role)
        defer.returnValue({
            PAYLOAD: {ROLE: role_name},
            STATUS: http.CREATED
        })

    @defer.inlineCallbacks
    def async_put(self, request):
        role_name = yield self._create_or_update_role(request, self._permissions.update_role)
        defer.returnValue({
            PAYLOAD: {ROLE: role_name},
            STATUS: http.OK
        })

    @defer.inlineCallbacks
    def _create_or_update_role(self, request, role_operation_fn):
        context = RequestContext.from_rest_request(request)
        payload = json.loads(request[PAYLOAD]) if PAYLOAD in request else None
        if not payload or not payload.get(ROLE):
            raise SpacebridgeApiRequestError('Request payload must contain the "role" parameter.',
                                             status_code=http.BAD_REQUEST)
        role = yield role_operation_fn(
            request_context=context,
            name=payload[ROLE],
            parent_roles=payload.get(IMPORTED_ROLES),
            general_capabilities=payload.get(GENERAL_CAPABILITIES),
            object_capabilities=[ObjectCapability.from_dict(oc) for oc in payload.get(OBJECT_CAPABILITIES, [])])
        defer.returnValue(role)

    @defer.inlineCallbacks
    def async_delete(self, request):
        context = RequestContext.from_rest_request(request)
        role = request.get(QUERY, {}).get(ROLE)
        if not role:
            raise SpacebridgeApiRequestError('Delete role request must specify the URL encoded parameter "role".',
                                             status_code=http.BAD_REQUEST)
        yield self._permissions.delete_role(context, role)
        defer.returnValue({
            PAYLOAD: {ROLE: role},
            STATUS: http.OK
        })
