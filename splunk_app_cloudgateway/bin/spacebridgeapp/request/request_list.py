"""
(C) 2019 Splunk Inc. All rights reserved.

Map of processing requests
"""
from spacebridgeapp.request.request_type import RequestType
from spacebridgeapp.request.alerts_request_processor import \
    process_alerts_list_request, process_alert_get_request, process_alerts_delete_request, process_alerts_clear_request
from spacebridgeapp.request.app_list_request_processor import \
    process_app_list_request, process_dashboard_app_list_get_request, process_dashboard_app_list_set_request
from spacebridgeapp.request.dashboard_request_processor import \
    process_dashboard_list_request, process_dashboard_get_request, process_dashboard_set_request, \
    process_dashboard_data_request
from spacebridgeapp.ar.websocket.asset_request_processor import \
    process_asset_get_request, process_asset_set_request, process_asset_delete_request
from spacebridgeapp.ar.websocket.ar_workspace_request_processor import \
    process_ar_workspace_set_request_v2, process_ar_workspace_get_request_v2, process_ar_workspace_delete_request_v2, \
    process_ar_workspace_image_set_request, process_ar_workspace_list_request, process_ar_workspace_format_request
from spacebridgeapp.nlp.request.jubilee_request_processor import process_jubilee_connection_info_request
from spacebridgeapp.request.version_request_processor import process_get_version_request
from spacebridgeapp.ar.websocket.location_request_processor import \
    process_beacon_region_get_request, process_beacon_region_set_request, process_beacon_region_delete_request, \
    process_geofence_dashboard_mapping_get_request, process_geofence_dashboard_mapping_get_all_request, \
    process_nearby_dashboard_mapping_get_request, process_nearby_dashboard_mapping_set_request, \
    process_nearby_dashboard_mapping_delete_request
from spacebridgeapp.nlp.request.nlp_request_processor import \
    process_dashboards_sync_request, process_saved_search_get_spl_request, process_saved_search_sync_request
from spacebridgeapp.request.client_config_request_processor import process_client_config_request
from spacebridgeapp.tv.request.group_request_processor import \
    process_group_get_request, process_group_set_request, process_group_delete_request
from spacebridgeapp.request.subscription_request_processor import \
    process_subscribe_request, process_unsubscribe_request, process_ping_request, process_subscribe_update_request
from spacebridgeapp.request.request_processor import process_device_credentials_validate_request
from spacebridgeapp.rest.clients.async_client_factory import FACTORY, KVSTORE, SPLUNK, JUBILEE, AR_PERMISSIONS, \
    SPACEBRIDGE
from spacebridgeapp.request.udf_request_processor import process_udf_hosted_resource_get
from spacebridgeapp.request.request_processor import process_complete_device_registration_request
from spacebridgeapp.ar.websocket.phantom_registration_processor import (
    process_phantom_registration_request, process_get_phantom_registration_info
)
from spacebridgeapp.request.drone_mode_request_processor import process_tv_get_request, process_tv_config_set_request, process_tv_bookmark_set_request, \
                                                                process_tv_bookmark_get_request, process_tv_bookmark_delete_request, process_tv_config_delete_request, \
                                                                process_tv_bookmark_activate_request, process_mpc_broadcast_request, process_tv_interaction_request, \
                                                                process_tv_captain_url_request, process_tv_config_bulk_set_request, process_tv_bookmark_activate_request

ENCRYPTION_CONTEXT = 'encryption_context'
# Add New Requests Here in format (request_type, process_function, async_client args to process_function)
REQUESTS = [
    (RequestType.ALERTS_LIST_REQUEST, process_alerts_list_request, [KVSTORE]),
    (RequestType.ALERTS_CLEAR_REQUEST, process_alerts_clear_request, [KVSTORE]),
    (RequestType.ALERT_GET_REQUEST, process_alert_get_request, [KVSTORE]),
    (RequestType.ALERT_DELETE_REQUEST, process_alerts_delete_request, [KVSTORE]),
    (RequestType.APP_LIST_REQUEST, process_app_list_request, [FACTORY]),
    (RequestType.DASHBOARD_APP_LIST_SET_REQUEST, process_dashboard_app_list_set_request, [FACTORY]),
    (RequestType.DASHBOARD_APP_LIST_GET_REQUEST, process_dashboard_app_list_get_request, [FACTORY]),
    (RequestType.DASHBOARD_LIST_REQUEST, process_dashboard_list_request, [FACTORY]),
    (RequestType.DASHBOARD_GET_REQUEST, process_dashboard_get_request, [FACTORY]),
    (RequestType.DASHBOARD_SET_REQUEST, process_dashboard_set_request, [KVSTORE]),
    (RequestType.DASHBOARD_DATA_REQUEST, process_dashboard_data_request, [FACTORY]),
    (RequestType.ASSET_GET_REQUEST, process_asset_get_request, [SPLUNK, KVSTORE, AR_PERMISSIONS]),
    (RequestType.ASSET_SET_REQUEST, process_asset_set_request, [KVSTORE, AR_PERMISSIONS]),
    (RequestType.ASSET_DELETE_REQUEST, process_asset_delete_request, [KVSTORE, AR_PERMISSIONS]),
    (RequestType.AR_WORKSPACE_SET_REQUEST_V2, process_ar_workspace_set_request_v2, [KVSTORE, AR_PERMISSIONS, SPLUNK]),
    (RequestType.AR_WORKSPACE_GET_REQUEST_V2, process_ar_workspace_get_request_v2, [KVSTORE, AR_PERMISSIONS]),
    (RequestType.AR_WORKSPACE_DELETE_REQUEST_V2, process_ar_workspace_delete_request_v2, [KVSTORE, AR_PERMISSIONS]),
    (RequestType.AR_WORKSPACE_IMAGE_SET_REQUEST, process_ar_workspace_image_set_request, [KVSTORE, AR_PERMISSIONS]),
    (RequestType.AR_WORKSPACE_LIST_REQUEST, process_ar_workspace_list_request, [KVSTORE, AR_PERMISSIONS]),
    (RequestType.AR_WORKSPACE_FORMAT_REQUEST, process_ar_workspace_format_request, []),
    (RequestType.JUBILEE_CONNECTION_INFO_REQUEST, process_jubilee_connection_info_request, [SPLUNK, JUBILEE]),
    (RequestType.VERSION_GET_REQUEST, process_get_version_request, [FACTORY]),
    (RequestType.TV_GET_REQUEST, process_tv_get_request, [KVSTORE]),
    (RequestType.TV_CONFIG_SET_REQUEST, process_tv_config_set_request, [FACTORY]),
    (RequestType.TV_CONFIG_BULK_SET_REQUEST, process_tv_config_bulk_set_request, [FACTORY]),
    (RequestType.TV_CONFIG_DELETE_REQUEST, process_tv_config_delete_request, [FACTORY]),
    (RequestType.TV_BOOKMARK_SET_REQUEST, process_tv_bookmark_set_request, [KVSTORE]),
    (RequestType.TV_BOOKMARK_GET_REQUEST, process_tv_bookmark_get_request, [KVSTORE]),
    (RequestType.TV_BOOKMARK_DELETE_REQUEST, process_tv_bookmark_delete_request, [KVSTORE]),
    (RequestType.TV_BOOKMARK_ACTIVATE_REQUEST, process_tv_bookmark_activate_request, [FACTORY]),
    (RequestType.START_MPC_BROADCAST_REQUEST, process_mpc_broadcast_request, [FACTORY]),
    (RequestType.TV_INTERACTION_REQUEST, process_tv_interaction_request, [FACTORY]),
    (RequestType.TV_CAPTAIN_URL_REQUEST, process_tv_captain_url_request, [FACTORY]),
    (RequestType.BEACON_REGION_GET_REQUEST, process_beacon_region_get_request, [KVSTORE]),
    (RequestType.BEACON_REGION_SET_REQUEST, process_beacon_region_set_request, [KVSTORE]),
    (RequestType.BEACON_REGION_DELETE_REQUEST, process_beacon_region_delete_request, [KVSTORE]),
    (
        RequestType.GEOFENCE_DASHBOARD_MAPPING_GET_REQUEST, process_geofence_dashboard_mapping_get_request,
        [KVSTORE, AR_PERMISSIONS]
    ),
    (
        RequestType.GEOFENCE_DASHBOARD_MAPPING_GET_ALL_REQUEST, process_geofence_dashboard_mapping_get_all_request,
        [KVSTORE, AR_PERMISSIONS]
    ),
    (
        RequestType.NEARBY_DASHBOARD_MAPPING_GET_REQUEST, process_nearby_dashboard_mapping_get_request,
        [KVSTORE, AR_PERMISSIONS]
    ),
    (
        RequestType.NEARBY_DASHBOARD_MAPPING_SET_REQUEST, process_nearby_dashboard_mapping_set_request,
        [KVSTORE, AR_PERMISSIONS]
    ),
    (
        RequestType.NEARBY_DASHBOARD_MAPPING_DELETE_REQUEST, process_nearby_dashboard_mapping_delete_request,
        [KVSTORE, AR_PERMISSIONS]
    ),
    (RequestType.CREATE_PHANTOM_REGISTRATION_REQUEST, process_phantom_registration_request, [KVSTORE]),
    (RequestType.GET_PHANTOM_REGISTRATION_INFO_REQUEST, process_get_phantom_registration_info, [KVSTORE]),
    (RequestType.NLP_SAVED_SEARCH_GET_SPL_REQUEST, process_saved_search_get_spl_request, [FACTORY]),
    (RequestType.NLP_SAVED_SEARCH_SYNC_REQUEST, process_saved_search_sync_request, [FACTORY]),
    (RequestType.NLP_DASHBOARDS_SYNC_REQUEST, process_dashboards_sync_request, [FACTORY]),
    (RequestType.CLIENT_CONFIG_REQUEST, process_client_config_request, []),
    (RequestType.GROUP_GET_REQUEST, process_group_get_request, [KVSTORE]),
    (RequestType.GROUP_SET_REQUEST, process_group_set_request, [KVSTORE]),
    (RequestType.GROUP_DELETE_REQUEST, process_group_delete_request, [KVSTORE]),
    (RequestType.UDF_HOSTED_RESOURCE_REQUEST, process_udf_hosted_resource_get,
     [KVSTORE, SPACEBRIDGE, ENCRYPTION_CONTEXT]),
    (RequestType.DEVICE_CREDENTIALS_VALIDATE_REQUEST, process_device_credentials_validate_request, [FACTORY]),
    (RequestType.COMPLETE_DEVICE_REGISTRATION_REQUEST, process_complete_device_registration_request, [FACTORY]),
]

# Add New Subscription Requests Here in format (request_type, process_function, async_client args to process_function)
SUBSCRIPTION_REQUESTS = [
    (RequestType.CLIENT_SUBSCRIBE_REQUEST, process_subscribe_request, [FACTORY]),
    (RequestType.CLIENT_UNSUBSCRIBE_REQUEST, process_unsubscribe_request, [KVSTORE]),
    (RequestType.CLIENT_SUBSCRIPTION_PING, process_ping_request, [FACTORY]),
    (RequestType.CLIENT_SUBSCRIPTION_UPDATE, process_subscribe_update_request, [KVSTORE]),
]
