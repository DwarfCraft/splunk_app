"""
Module to process Location Related Requests
"""
import json
import math

from google.protobuf.json_format import MessageToJson
from spacebridgeapp.ar.data.beacon_geofence_data import BeaconRegion
from spacebridgeapp.ar.data import beacon_geofence_data
from spacebridgeapp.ar.storage.queries import get_query_matching_keys
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError, SpacebridgeARPermissionError
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.ar.permissions.async_permissions_client import Capabilities, AccessQuantity, ARObjectType
from spacebridgeapp.util import constants
from splapp_protocol import common_pb2
from twisted.internet import defer
from twisted.web import http

LOGGER = setup_logging('{}_location_request_processor'.format(constants.SPACEBRIDGE_APP_NAME),
                       'location_request_processor')

BEACON_READ_PERMISSION_REQUIRED = constants.VIEW_PERMISSION_REQUIRED.format(object_type='beacon')
BEACON_WRITE_PERMISSION_REQUIRED = constants.MODIFY_PERMISSION_REQUIRED.format(object_type='beacon')
BEACON_MANAGE_PERMISSION_REQUIRED = constants.MANAGE_PERMISSION_REQUIRED.format(object_type='beacon')
GEOFENCE_READ_PERMISSION_REQUIRED = constants.VIEW_PERMISSION_REQUIRED.format(object_type='geofence')
GEOFENCE_WRITE_PERMISSION_REQUIRED = constants.MODIFY_PERMISSION_REQUIRED.format(object_type='geofence')
GEOFENCE_MANAGE_PERMISSION_REQUIRED = constants.MANAGE_PERMISSION_REQUIRED.format(object_type='geofence')


@defer.inlineCallbacks
def process_beacon_region_get_request(request_context,
                                      client_single_request,
                                      server_single_response,
                                      async_kvstore_client):
    """Returns all beacon regions in KV store."""
    response = yield async_kvstore_client.async_kvstore_get_request(constants.AR_BEACON_REGIONS_COLLECTION_NAME,
                                                                    request_context.auth_header)
    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError("Call to Beacon Regions GET failed with code={} message={}"
                                         .format(response.code, message), status_code=response.code)

    LOGGER.info("Call to Beacon Regions GET succeeded with code=%d", response.code)
    response_json = yield response.json()
    server_single_response.beaconRegionGetResponse.beaconRegions.extend(
        BeaconRegion.from_json(region).to_protobuf() for region in response_json
    )


@defer.inlineCallbacks
def process_beacon_region_set_request(request_context,
                                      client_single_request,
                                      server_single_response,
                                      async_kvstore_client):
    """Processes nearby dashboard mapping set requests and sets/overwrites a dashboard mapping for the nearby entity."""
    kv_store_key = client_single_request.beaconRegionSetRequest.beaconRegion.uuid
    title = client_single_request.beaconRegionSetRequest.beaconRegion.title
    json_body = {
        constants.KEY: kv_store_key,
        constants.UUID: kv_store_key,
        constants.TITLE: title
    }
    response = yield async_kvstore_client.async_kvstore_post_request(constants.AR_BEACON_REGIONS_COLLECTION_NAME,
                                                                     data=json.dumps(json_body),
                                                                     auth_header=request_context.auth_header,
                                                                     key_id=kv_store_key)
    message = yield response.text()
    status_code = response.code
    if kv_store_key and status_code == http.NOT_FOUND:
        response = yield async_kvstore_client.async_kvstore_post_request(constants.AR_BEACON_REGIONS_COLLECTION_NAME,
                                                                         data=json.dumps(json_body),
                                                                         auth_header=request_context.auth_header)
        message = yield response.text()
        status_code = response.code

    if status_code not in {http.OK, http.CREATED}:
        raise SpacebridgeApiRequestError(
            "Call to AR workspace BEACON REGION SET failed with code={} message={}".format(status_code, message),
            status_code=status_code)
    server_single_response.beaconRegionSetResponse.SetInParent()
    LOGGER.info("Call to BEACON REGION SET succeeded with code=%d message=%s", status_code, message)


@defer.inlineCallbacks
def process_beacon_region_delete_request(request_context,
                                         client_single_request,
                                         server_single_response,
                                         async_kvstore_client):
    """This processes beacon region delete requests as indicated by the client."""
    beacon_uuids = client_single_request.beaconRegionDeleteRequest.beaconRegionUUIDs
    response = yield async_kvstore_client.async_kvstore_delete_request(
        constants.AR_BEACON_REGIONS_COLLECTION_NAME, auth_header=request_context.auth_header,
        params={constants.QUERY: get_query_matching_keys(beacon_uuids)})
    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError('Failed to delete beacons={} message="{}" status_code={}'.format(
            beacon_uuids, message, response.code), status_code=response.code)
    server_single_response.beaconRegionDeleteResponse.SetInParent()


@defer.inlineCallbacks
def process_geofence_dashboard_mapping_get_request(request_context,
                                                   client_single_request,
                                                   server_single_response,
                                                   async_kvstore_client,
                                                   async_ar_permissions_client):
    """
    This method processes geofence dashboard mapping get requests, returning the NearbyEntity protobuf objects stored in
    the kvstore within the NearbyDashboardMappingGetResponse.
    """
    # TODO: Implement some sort of data structure to partition geofences so we're not always
    # fetching every single geofence and then sorting it
    geofence_access = yield async_ar_permissions_client.get_accessible_objects(
        request_context, Capabilities.GEOFENCE_READ)
    if geofence_access.quantity == AccessQuantity.NONE:
        del server_single_response.geofenceDashboardMappingGetResponse.mappings[:]
        server_single_response.geofenceDashboardMappingGetResponse.mappings.extend([])
        return

    params = (
        {constants.QUERY: get_query_matching_keys(geofence_access.ids)}
        if geofence_access.quantity == AccessQuantity.SOME else
        None
    )
    response = yield async_kvstore_client.async_kvstore_get_request(constants.AR_GEOFENCES_COLLECTION_NAME,
                                                                    request_context.auth_header, params=params)
    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError('Failed to lookup geofences with query={} message={} status_code={}'.format(
            params, message, response.code), status_code=response.code)

    mapping_list = yield response.json()
    coordinates = client_single_request.geofenceDashboardMappingGetRequest.userCoordinates
    geofence_limit = client_single_request.geofenceDashboardMappingGetRequest.limit
    (latitude, longitude) = (coordinates.latitude, coordinates.longitude)
    validate_coordinates(latitude, longitude)

    # read json_string into list
    for mapping in mapping_list:
        mapping['nearby_entity'] = json.loads(mapping['nearby_entity'])

    # sort list
    mapping_list = sorted(mapping_list, key=lambda x: geofence_sort_key(latitude, longitude, x))[:geofence_limit]

    # convert mapping to proto before adding it to the server_single_response
    del server_single_response.geofenceDashboardMappingGetResponse.mappings[:]
    server_single_response.geofenceDashboardMappingGetResponse.mappings.extend(
        construct_dashboard_mapping_list(mapping_list))


@defer.inlineCallbacks
def process_geofence_dashboard_mapping_get_all_request(request_context,
                                                       client_single_request,
                                                       server_single_response,
                                                       async_kvstore_client,
                                                       async_ar_permissions_client):
    """
    This method processes geofence dashboard mapping get_all requests, returning the NearbyEntity protobuf objects
    stored in the kvstore within the NearbyDashboardMappingGetAllResponse.
    """
    geofence_access = yield async_ar_permissions_client.get_accessible_objects(
        request_context, Capabilities.GEOFENCE_READ)
    if geofence_access.quantity == AccessQuantity.NONE:
        server_single_response.geofenceDashboardMappingGetAllResponse.SetInParent()
        return

    params = (
        {constants.QUERY: get_query_matching_keys(geofence_access.ids)}
        if geofence_access.quantity == AccessQuantity.SOME else
        None
    )
    response = yield async_kvstore_client.async_kvstore_get_request(constants.AR_GEOFENCES_COLLECTION_NAME,
                                                                    request_context.auth_header, params=params)
    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError(
            'Failed to lookup geofences with query={} message={} status_code={}'.format(params, response.code, message),
            status_code=response.code)

    mapping_list = yield response.json()

    # read json_string into list
    for mapping in mapping_list:
        mapping['nearby_entity'] = json.loads(mapping['nearby_entity'])

    # convert mapping to proto before adding it to the server_single_response
    del server_single_response.geofenceDashboardMappingGetAllResponse.mappings[:]
    server_single_response.geofenceDashboardMappingGetAllResponse.mappings.extend(
        construct_dashboard_mapping_list(mapping_list))


@defer.inlineCallbacks
def process_nearby_dashboard_mapping_get_request(request_context,
                                                 client_single_request,
                                                 server_single_response,
                                                 async_kvstore_client,
                                                 async_ar_permissions_client):
    """
    This method processes nearby dashboard mapping get requests, returning the NearbyEntity protobuf
    objects stored in the kvstore within the NearbyDashboardMappingGetResponse.
    """
    beacon_access = yield async_ar_permissions_client.get_accessible_objects(request_context, Capabilities.BEACON_READ)
    if beacon_access.quantity == AccessQuantity.NONE:
        server_single_response.nearbyDashboardMappingGetResponse.SetInParent()
        return

    entity_keys = client_single_request.nearbyDashboardMappingGetRequest.nearbyEntityKeys
    beacon_keys = []
    for entity_key in entity_keys:
        key = make_kvstore_beacon_key(entity_key.beaconKey)
        if beacon_access.quantity == AccessQuantity.ALL or key in beacon_access.ids:
            beacon_keys.append(key)
    params = {constants.QUERY: get_query_matching_keys(beacon_keys)} if beacon_keys else None
    response = yield async_kvstore_client.async_kvstore_get_request(constants.AR_BEACONS_COLLECTION_NAME,
                                                                    request_context.auth_header,
                                                                    params=params)
    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError("Call to Nearby dashboard mapping GET failed with code={} message={}"
                                         .format(response.code, message), status_code=response.code)

    mapping_list = yield response.json()
    for mapping in mapping_list:
        mapping['nearby_entity'] = json.loads(mapping['nearby_entity'])

    del server_single_response.nearbyDashboardMappingGetResponse.mappings[:]
    server_single_response.nearbyDashboardMappingGetResponse.mappings.extend(
        construct_dashboard_mapping_list(mapping_list))
    LOGGER.info("Call to Beacon dashboard mapping GET succeeded with code=%d", response.code)


@defer.inlineCallbacks
def process_nearby_dashboard_mapping_set_request(request_context,
                                                 client_single_request,
                                                 server_single_response,
                                                 async_kvstore_client,
                                                 async_ar_permissions_client):
    """
    This method processes nearby dashboard mapping set requests and sets/overwrites a dashboard mapping for the
    nearbyEntity.
    """
    request = client_single_request.nearbyDashboardMappingSetRequest
    nearby_entity = request.mapping.nearbyEntity
    dashboard_ids = request.mapping.dashboardIDs

    is_beacon = nearby_entity.HasField('beaconDefinition')
    kv_store_collection = constants.AR_BEACONS_COLLECTION_NAME if is_beacon else constants.AR_GEOFENCES_COLLECTION_NAME
    if is_beacon:
        kv_store_key = make_kvstore_beacon_key(nearby_entity.beaconDefinition.key)
    else:
        kv_store_key = nearby_entity.geofenceDefinition.key
        latitude = nearby_entity.geofenceDefinition.circularGeofence.center.latitude
        longitude = nearby_entity.geofenceDefinition.circularGeofence.center.longitude
        validate_coordinates(latitude, longitude)

    yield async_ar_permissions_client.check_object_permission(
        request_context, Capabilities.BEACON_WRITE if is_beacon else Capabilities.GEOFENCE_WRITE, kv_store_key)

    json_body = {
        constants.KEY: kv_store_key,
        constants.NEARBY_ENTITY: MessageToJson(nearby_entity, including_default_value_fields=True),
        constants.DASHBOARD_IDS: [str(x) for x in dashboard_ids]
    }
    response = yield async_kvstore_client.async_kvstore_post_request(kv_store_collection,
                                                                     data=json.dumps(json_body),
                                                                     auth_header=request_context.auth_header)
    status_code = response.code
    if status_code == http.CONFLICT:
        response = yield async_kvstore_client.async_kvstore_post_request(kv_store_collection,
                                                                         data=json.dumps(json_body),
                                                                         auth_header=request_context.auth_header,
                                                                         key_id=kv_store_key)
        status_code = response.code
    if status_code not in {http.OK, http.CREATED}:
        message = yield response.text()
        raise SpacebridgeApiRequestError(
            'Failed to update {}={} message={} status_code={}'.format(
                'beacon' if is_beacon else 'geofence', kv_store_key, message, status_code),
            status_code=status_code)

    if status_code == http.CREATED:
        async_ar_permissions_client.register_objects(request_context,
                                                     ARObjectType.BEACON if is_beacon else ARObjectType.GEOFENCE,
                                                     [kv_store_key])

    server_single_response.nearbyDashboardMappingSetResponse.SetInParent()


@defer.inlineCallbacks
def process_nearby_dashboard_mapping_delete_request(request_context,
                                                    client_single_request,
                                                    server_single_response,
                                                    async_kvstore_client,
                                                    async_ar_permissions_client):
    """This processes dashboard mapping delete requests as indicated by the client."""
    entity_keys = client_single_request.nearbyDashboardMappingDeleteRequest.nearbyEntityKeys
    if not entity_keys:
        raise SpacebridgeApiRequestError('Must specify entity keys to delete.', status_code=http.BAD_REQUEST)

    keys = []
    kv_store_collection = constants.AR_GEOFENCES_COLLECTION_NAME
    for key in entity_keys:
        if key.HasField('beaconKey'):
            kv_store_key = make_kvstore_beacon_key(key.beaconKey)
            kv_store_collection = constants.AR_BEACONS_COLLECTION_NAME
        else:
            kv_store_key = key.geofenceKey
            kv_store_collection = constants.AR_GEOFENCES_COLLECTION_NAME
        keys.append(kv_store_key)

    yield async_ar_permissions_client.check_permission(request_context, (
        Capabilities.GEOFENCE_MANAGE
        if kv_store_collection == constants.AR_GEOFENCES_COLLECTION_NAME
        else Capabilities.BEACON_MANAGE
    ))

    response = yield async_kvstore_client.async_kvstore_delete_request(
        collection=kv_store_collection, auth_header=request_context.auth_header,
        params={constants.QUERY: get_query_matching_keys(keys)})
    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError(
            'Failed to delete ids={} from collection={} message={} status_code={}'.format(
                keys, kv_store_collection, message, response.code), status_code=response.code)

    yield async_ar_permissions_client.delete_objects(request_context, keys)

    server_single_response.nearbyDashboardMappingDeleteResponse.SetInParent()


def construct_dashboard_mapping_list(response_list):
    """
    Function to construct a proto response list from
    a kvstore response

    :param response_list: list of kvstore mapping entries
    :return: list of nearbyDashboardMapping protos
    """
    mappings = []
    for response in response_list:
        mapping = common_pb2.NearbyDashboardMapping()
        entity = beacon_geofence_data.NearbyEntity.from_json(response['nearby_entity']).to_protobuf()
        mapping.nearbyEntity.CopyFrom(entity)
        mapping.dashboardIDs[:] = response['dashboard_ids']
        mappings.append(mapping)

    return mappings


def geofence_sort_key(latitude, longitude, mapping):
    geofence = mapping['nearby_entity']['geofenceDefinition']['circularGeofence']
    fence_latitude = geofence['center']['latitude']
    fence_longitude = geofence['center']['longitude']
    fence_radius = geofence['radius']
    return math.sqrt(abs(latitude - fence_latitude) + abs(longitude - fence_longitude)) - fence_radius


def make_kvstore_beacon_key(key):
    return '{}_{}_{}'.format(key.uuid, key.major, key.minor)


def validate_coordinates(latitude, longitude):
    if not (-90 <= latitude <= 90 or -180 <= longitude <= 180):
        raise SpacebridgeApiRequestError(
            "Request failed due to invalid coordinates (latitude={latitude}, longitude={longitude})".format(
                latitude=latitude, longitude=longitude), status_code=400)
