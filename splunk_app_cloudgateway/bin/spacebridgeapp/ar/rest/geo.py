import sys
import json

from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from spacebridgeapp.ar.ar_util import wait_for_all
from spacebridgeapp.ar.permissions.async_permissions_client import AccessQuantity, ARObjectType, Capabilities
from spacebridgeapp.ar.storage.queries import get_query_matching_keys
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.messages.request_context import RequestContext
from spacebridgeapp.rest import async_base_endpoint
from spacebridgeapp.util.constants import (
    STATUS, PAYLOAD, KEY, AR_BEACONS_COLLECTION_NAME, AR_GEOFENCES_COLLECTION_NAME, QUERY
)
from twisted.internet import defer
from twisted.web import http


ID = 'id'
TITLE = 'title'
TYPE = 'type'
NEARBY_ENTITY = 'nearby_entity'


class Geo(async_base_endpoint.AsyncBaseRestHandler):

    @defer.inlineCallbacks
    def async_get(self, request):
        context = RequestContext.from_rest_request(request)
        location_based_assets = yield wait_for_all([
            self._get_beacons(context),
            self._get_geofences(context)
        ], raise_on_first_exception=True)

        payload = []
        for grouping in location_based_assets:
            payload.extend(grouping)

        defer.returnValue({
            STATUS: http.OK,
            PAYLOAD: payload
        })

    @defer.inlineCallbacks
    def _get_beacons(self, context):
        beacons = yield self._lookup_location_based_assets(
            context, AR_BEACONS_COLLECTION_NAME, ARObjectType.BEACON, Capabilities.BEACON_READ)
        defer.returnValue(beacons)

    @defer.inlineCallbacks
    def _get_geofences(self, context):
        geofences = yield self._lookup_location_based_assets(
            context, AR_GEOFENCES_COLLECTION_NAME, ARObjectType.GEOFENCE, Capabilities.GEOFENCE_READ)
        defer.returnValue(geofences)

    @defer.inlineCallbacks
    def _lookup_location_based_assets(self, context, collection, object_type, capability):
        permissions = self.async_client_factory.ar_permissions_client()
        kvstore = self.async_client_factory.kvstore_client()

        access = yield permissions.get_accessible_objects(context, capability)
        if access.quantity == AccessQuantity.NONE:
            defer.returnValue([])

        params = None if access.quantity == AccessQuantity.ALL else {QUERY: get_query_matching_keys(access.ids)}
        response = yield kvstore.async_kvstore_get_request(
            collection=collection, auth_header=context.auth_header, params=params)
        if response.code != http.OK:
            message = yield response.text()
            raise SpacebridgeApiRequestError(
                'Failed to lookup entities from collection={} message={} status_code={}'.format(
                    collection, message, response.code), status_code=response.code)
        response_json = yield response.json()

        entries = []
        for entry in response_json:
            nearby_entity = json.loads(entry[NEARBY_ENTITY])
            entries.append({
                ID: entry[KEY],
                TITLE: nearby_entity[TITLE],
                TYPE: object_type.value
            })
        defer.returnValue(entries)
