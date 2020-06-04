"""
(C) 2019 Splunk Inc. All rights reserved.

Constants file for constants referenced throughout project
"""

# App Name
SPACEBRIDGE_APP_NAME = "splunk_app_cloudgateway"
SPLAPP_APP_ID = "com.splunk.mobile.cloudgatewayapp"
CLOUDGATEWAY = "cloudgateway"

# Other Apps
SPLUNK_DASHBOARD_APP = "splunk-dashboard-app"
UDF_IMAGE_RESOURCE_COLLECTION = "splunk-dashboard-images"
UDF_ICON_RESOURCE_COLLECTION = "splunk-dashboard-icons"

# Splunk
NOBODY = "nobody"
ADMIN = 'admin'
VALUE = 'value'
LABEL = 'label'
MATCH = 'match'

# storage/passwords constants
NAME = 'name'
PASSWORD = 'password'
CONTENT_TYPE_FORM_ENCODED = 'application/x-www-form-urlencoded'
AUTHTOKEN = 'authtoken'
SYSTEM_AUTHTOKEN = 'system_authtoken'
SESSION = 'session'
USER = 'user'
USERNAME = 'username'
SYSTEM_AUTHTOKEN = 'system_authtoken'
JWT_TOKEN_TYPE = 'splunk.jwt.token'
SPLUNK_SESSION_TOKEN_TYPE = 'splunk.session.token'
COOKIES = 'cookies'
SPLUNKD_8000 = 'splunkd_8000'
CONTENT = 'content'
ENTRY = 'entry'
SAML = 'SAML'

# spacebridge message events
UNREGISTER_EVENT = "unregisterEvent"
MDM_REGISTRATION_REQUEST = "mdmRegistrationRequest"

# conf file constants
KVSTORE = 'kvstore'
MAX_DOCUMENTS_PER_BATCH_SAVE = 'max_documents_per_batch_save'

# KV Store Constants
REGISTERED_DEVICES_COLLECTION_NAME = "registered_devices"
UNCONFIRMED_DEVICES_COLLECTION_NAME = "unconfirmed_devices"
APPLICATION_TYPES_COLLECTION_NAME = "application_types"
FEATURES_COLLECTION_NAME = "features"
MOBILE_ALERTS_COLLECTION_NAME = "mobile_alerts"
REGISTERED_USERS_COLLECTION_NAME = "registered_users"
ALERTS_RECIPIENT_DEVICES_COLLECTION_NAME = "alert_recipient_devices"
AR_DASHBOARDS_COLLECTION_NAME = "ar_dashboards"
AR_PERMISSIONS_COLLECTION_NAME = "ar_permissions"
AR_BEACONS_COLLECTION_NAME = "ar_beacons"
AR_BEACON_REGIONS_COLLECTION_NAME = "ar_beacon_regions"
AR_GEOFENCES_COLLECTION_NAME = "ar_geofences"
AR_WORKSPACES_COLLECTION_NAME = "ar_workspaces"
ASSETS_COLLECTION_NAME = "assets"
ASSET_GROUPS_COLLECTION_NAME = "asset_groups"
META_COLLECTION_NAME = "meta"
SUBSCRIPTIONS_COLLECTION_NAME = "subscriptions"
SUBSCRIPTION_CREDENTIALS_COLLECTION_NAME = "subscription_credentials"
SEARCH_UPDATES_COLLECTION_NAME = "subscription_updates"
SEARCHES_COLLECTION_NAME = "searches"
SEARCH_UPDATES_COLLECTION_NAME = "search_updates"
DASHBOARD_META_COLLECTION_NAME = "dashboard_meta"
DEVICE_PUBLIC_KEYS_COLLECTION_NAME = "device_public_keys"
USER_META_COLLECTION_NAME = "user_meta"
DEVICE_ROLES_COLLECTION_NAME = "device_role_mapping"
GROUPS_COLLECTION_NAME = "groups"
DRONE_MODE_TVS_COLLECTION_NAME = "drone_mode_tvs"
DRONE_MODE_IPADS_COLLECTION_NAME = "drone_mode_ipads"
TV_BOOKMARK_COLLECTION_NAME = "tv_bookmark"
DASHBOARD_APP_LIST = "dashboard_app_list"
ORIGINAL_WORKSPACE_FIELD = "original_workspace"
LAST_MODIFIED = "last_modified"
WORKSPACE_DATA = "workspace_data"
USER_KEY = "_user"
TIMESTAMP = "timestamp"
ROLE = "role"
SEARCH_KEY = "search_key"
SUBSCRIPTION_KEY = "subscription_key"
SUBSCRIPTION_TYPE = "subscription_type"
PARENT_SEARCH_KEY = "parent_search_key"
SHARD_ID = "shard_id"
ID_HASH = "id_hash"
BASE = "base"
DASHBOARD_ID = "dashboard_id"
DASHBOARD_IDS = "dashboard_ids"
NEARBY_ENTITY = "nearby_entity"
APP_LIST = 'app_list'
APP_NAMES = 'app_names'
SEARCH = 'search'
DRONE_MODE_KEY = 'drone_mode'
RESOURCE_TYPE = 'resource_type'
MINIMAL_LIST = 'minimal_list'
MAX_RESULTS = 'max_results'
OFFSET = 'offset'
DEVICE_ID = 'device_id'
VERSION = 'version'
LAST_UPDATE_TIME = 'last_update_time'
BATCH_SAVE = 'batch_save'
LIMIT = 'limit'
TTL_SECONDS = 'ttl_seconds'
EXPIRED_TIME = 'expired_time'
DRONE_MODE_TV = 'drone_mode_tv'
DRONE_MODE_IPAD = 'drone_mode_ipad'

# Form inputs constants
TIMEPICKER = 'timepicker'
DROPDOWN = 'dropdown'
RADIO = 'radio'
CHECKBOX = 'checkbox'
TEXTBOX = 'textbox'
MULTISELECT = 'multiselect'
TOKEN_NAME = 'tokenName'
DEFAULT_VALUE = 'defaultValue'
DEPENDS = 'depends'
REJECTS = 'rejects'
INPUT_TOKENS = 'input_tokens'


# Drone mode constants
TV_CONFIG = 'tv_config'
TV_CONFIG_ID = 'tv_config_id'
TV_CONFIG_MAP = 'tv_config_map'
TV_CATEGORY_ID = 'tv_category_id'
TV_LAYOUT = 'tv_layout'
TV_GRID = 'tv_grid'
DEVICE_IDS = 'device_ids'
GRID = 'grid'
HEIGHT = 'height'
WIDTH = 'width'
POSITION = 'position'
CAPTAIN_ID = 'captain_id'
CAPTAIN_URL = 'captain_url'
UPDATE_FLAG = 'update_flag'
IS_ACTIVE = 'is_active'
DISPLAY_NAME = 'display_name'
ADMIN_ALL_OBJECTS = 'admin_all_objects'
CONTENT = 'content'
FAVORITE = 'favorite'
IS_FAVORITE = 'is_favorite'
UNKNOWN_MODE = 0
DASHBOARD_MODE = 1
IMAGE_MODE = 2
VIDEO_MODE = 3
DASHBOARD_GROUP_MODE = 4
OFF_MODE = 5
MODE = 'mode'
ID = 'id'
DEVICE_NAME = 'device_name'
REQUEST_TYPE = 'request_type'
UNKNOWN_REQUEST_TYPE = 0
CREATE_REQUEST_TYPE = 1
EDIT_REQUEST_TYPE = 2
REQUEST_CONTEXT = 'request_context'
BOOKMARK_DESCRIPTION = 'description'
DEVICE_ID_LIST = 'device_id_list'
SLIDESHOW_DURATION = 'slideshow_duration'
DEFAULT_SLIDESHOW_DURATION = 30
MPC_BROADCAST = 'mpc_broadcast'
TV_INTERACTION = 'tv_interaction'
SLIDESHOW_GOTO = 'slideshow_go_to'
SLIDESHOW_STOP = 'slideshow_stop'
SLIDESHOW_FORWARD = 'slideshow_forward'
SLIDESHOW_BACK = 'slideshow_back'
SLIDESHOW_SPEED = 'slideshow_speed'
IPAD_APP_ID_PROD = 'com.splunk.mobile.DroneController'
IPAD_APP_ID_DEV = 'com.splunk.mobile.DroneTV'
APP_ID = 'app_id'
INPUT_CHOICES = 'input_choices'
USER_CHOICES = 'user_choices'

# Registered Devices KV STORE Field Names
REGISTERED_DEVICES_DEVICE_ID = "device_id"
REGISTERED_DEVICES_DEVICE_TYPE = "device_type"

# Module Level Constants
CLIENT_SINGLE_REQUEST = "clientSingleRequest"
CLIENT_SUBSCRIPTION_MESSAGE = "clientSubscriptionMessage"

# Server Subscription Constants
SERVER_SUBSCRIPTION_RESPONSE = "serverSubscriptionResponse"
SERVER_SUBSCRIBE_RESPONSE = "serverSubscribeResponse"
SERVER_SUBSCRIBE_UPDATE_RESPONSE = "serverSubscribeUpdateResponse"
DRONE_MODE_TV_SUBSCRIBE = "droneModeTVSubscribe"
DRONE_MODE_IPAD_SUBSCRIBE = "droneModeiPadSubscribe"

# Client Subscribe Subscription Constants
CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_REQUEST = "dashboardVisualizationSubscribe"
CLIENT_SUBSCRIBE_DASHBOARD_INPUT_SEARCH_REQUEST = "dashboardInputSearchSubscribe"
CLIENT_SUBSCRIBE_SAVED_SEARCH_REQUEST = "clientSavedSearchSubscribe"
CLIENT_SUBSCRIBE_UDF_DATASOURCE = "udfDataSourceSubscribe"
CLIENT_SUBSCRIBE_DRONE_MODE_TV = "droneModeTVSubscribe"
CLIENT_SUBSCRIBE_DRONE_MODE_IPAD = "droneModeiPadSubscribe"

# Client Subscribe Subscription Update Constants
CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_CLUSTER_MAP = "dashboardVisualizationClusterMap"
CLIENT_SUBSCRIBE_DASHBOARD_VISUALIZATION_CHOROPLETH_MAP = "dashboardVisualizationChoroplethMap"

# Search Job Constants
EXEC_MODE_ONESHOT = 'oneshot'
EXEC_MODE_NORMAL = 'normal'

# Subscription Search Constants
ROOT = 'root'
SAVED_SEARCH_ARGS_PREFIX = "args."
SUBSCRIPTION_VERSION_2 = 2

#
DEPLOYMENT_INFO = "deployment_info"
DEPLOYMENT_FRIENDLY_NAME = "friendly_name"
DEPLOYMENT_ID = "deployment_id"
INSTANCE_ID = "instanceId"

# Registration Constants
ENCRYPTION_KEYS = "encryption_keys"
MDM_SIGN_PUBLIC_KEY = "mdm_sign_public_key"
MDM_SIGN_PRIVATE_KEY = "mdm_sign_private_key"
PUBLIC_KEY = "public_key"
SIGN_PUBLIC_KEY = "sign_public_key"
SIGN_PRIVATE_KEY = "sign_private_key"
ENCRYPT_PUBLIC_KEY = "encrypt_public_key"
ENCRYPT_PRIVATE_KEY = "encrypt_private_key"
SERVER_VERSION = "server_version"
MDM_KEYPAIR_GENERATION_TIME = "mdm_keypair_generation_time"
CREATED = "created"

# KV STORE OPERATORS
AND_OPERATOR = "$and"
OR_OPERATOR = "$or"
LESS_THAN_OPERATOR = "$lt"
GREATER_THAN_OPERATOR = "$gt"
GREATER_THAN_OR_EQUAL_TO_OPERATOR = "$gte"
NOT_EQUAL = "$ne"
SORT = "sort"
LIMIT = "limit"
FIELDS = "fields"
QUERY = "query"
POST_SEARCH = "post_search"
KEY = "_key"
SKIP = 'skip'

# TELEMETRY
TELEMETRY_INSTANCE_ID = "telemetry_instance_id"
SPLUNK_VERSION = "server_version"
ON_CLOUD_INSTANCE = "on_cloud_instance"
INSTALLATION_ENVIRONMENT = "installation_environment"
ENTERPRISE = "enterprise"
CLOUD = "cloud"

# App Name
ALERTS_IOS = "Alerts iOS"
APPLE_TV = "Apple TV"
AR_PLUS = "AR+"
VR = "VR"
NLP = "NLP"
DRONE_MODE = "Drone Mode"
DRONE_IPAD = "Drone Mode iPad"

# Device Platform
IOS = "iOS"
ANDROID = "Android"

# Environment Variables
ENV_E2E_ENCRYPTION = "MOBILE_E2E_ENCRYPTION"
ENV_OPTION_ON = "1"

# Performance Constants
MAX_PAYLOAD_SIZE_BYTES = 1000000.0  # 1mb
TIMEOUT_SECONDS = 10

HEADERS = 'headers'
HEADER_AUTHORIZATION = 'Authorization'
HEADER_CONTENT_TYPE = 'Content-Type'
HEADER_USER_AGENT = 'User-Agent'
OUTPUT_MODE = 'output_mode'
JSON = 'json'
COUNT = 'count'

APPLICATION_JSON = 'application/json; charset=utf-8'

# Form Dashboards
MAX_TOKEN_CHARACTERS = 50

# Default ports
DEFAULT_HTTP_PORT = 80
DEFAULT_HTTPS_PORT = 443

# Alerts constants
SERVER_URI = "server_uri"
SUBJECT = "alert_subject"
DESCRIPTION = "alert_description"
SEVERITY = "alert_severity"
CALL_TO_ACTION_URL = "alert_call_to_action_url"
CALL_TO_ACTION_LABEL = "alert_call_to_action_label"
ALERT_TIMESTAMP_FIELD = "alert_time"
ALERT_DASHBOARD_ID = "alert_dashboard_id"
ALERT_DASHBOARD_DATA = "alert_dashboard_data"
DASHBOARD_TOGGLE = "dashboard_toggle"
ALERT_RECIPIENTS = "alert_recipients"
ALERT_ID = "alert_id"
ALERT_MESSAGE = "alert_message"
ALERT_SUBJECT = "alert_subject"
CONFIGURATION = "configuration"
SAVED_SEARCH_RESULT = "result"
MESSAGE = "alert_message"
SESSION_KEY = "session_key"
RESULTS_LINK = "results_link"
SEARCH_ID = "sid"
OWNER = "owner"
APP_NAME = "app"
SEARCH_NAME = "search_name"
ATTACH_DASHBOARD_TOGGLE = "1"
ATTACH_TABLE_TOGGLE = "2"
TOKEN = "token_name"
FIELDNAME = "result_fieldname"
RESULT = "result"
ALL_USERS = "all"

# AR constants
AR_WORKSPACE_VERION_KEY = "workspace_version"
AR_WORKSPACE_VERION = 1
TITLE = 'title'
UUID = 'uuid'
BEACON = 'beacon'
GEOFENCE = 'geofence'
BEACON_DEFINITION = 'beaconDefinition'
GEOFENCE_DEFINITION = 'geofenceDefinition'
VALID_TOKEN_NAME = "ar.assetID"
VALID_CHART_TYPES = ('fillerGauge', 'radialGauge', 'markerGauge')
ASSET = 'asset'
ASSETS = 'assets'
ASSET_DATA = 'asset_data'
ASSET_OBJECTS = 'asset_objects'
ASSET_NAME = 'asset_name'
ASSET_TYPE = 'asset_type'
ASSET_ID = 'asset_id'
ASSET_IDS = 'asset_ids'
ASSET_GROUP = 'asset_group'
ASSET_GROUPS = 'asset_groups'
ASSET_GROUP_ID = 'asset_group_id'
ASSET_GROUP_IDS = 'asset_group_ids'
ASSET_GROUP_NAME = 'asset_group_name'
ASSET_GROUP_OBJECTS = 'asset_group_objects'
USER_PROVIDED = 'user_provided'
SPLUNK_GENERATED = 'splunk_generated'
IS_SPLUNK_GENERATED = 'is_splunk_generated'
DASHBOARD = 'dashboard'
DASHBOARD_ID_KEY = 'dashboardId'
AR_WORKSPACE_ID_KEY = 'arWorkspaceId'
NEW_WORKSPACE_TITLE = 'new_workspace_title'
IS_AR = 'is_ar'

# AR permissions constants
VIEW_PERMISSION_REQUIRED = ('Users must have ar_write, {object_type}_read, {object_type}_write, or '
                            '{object_type}_manage to view {object_type}s.')
MODIFY_PERMISSION_REQUIRED = ('Users must have ar_write, {object_type}_write, or {object_type}_manage to modify '
                              '{object_type}s.')
MANAGE_PERMISSION_REQUIRED = 'Users must have ar_write or {object_type}_manage to create or delete {object_type}s.'
PERMISSIONS = 'permissions'
AR_WRITE = 'ar_write'

BODY = 'body'
WORKSPACE_ID = 'workspace_id'
INTEGRITY_HASH = 'integrity_hash'
PAYLOAD = 'payload'
STATUS = 'status'

ACTION = 'action'
CREATE = 'create'
UPDATE = 'update'
DELETE = 'delete'
POST = 'post'
GET = 'get'
POST_OR_UPDATE = 'post_or_update'

