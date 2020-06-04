# Copyright 2016 Splunk Inc. All rights reserved.

import em_path_inject  # noqa
from utils.i18n_py23 import _

APP_NAME = 'splunk_app_infrastructure'

STORE_COLLECTORS = 'em_collector_configs'
STORE_GROUPS = 'em_groups'
STORE_CLOUD_CONFIGS = 'em_cloud_configs'

# NOTE: if you were to change the name of the kvstore cache, make sure corresponding
# changes are made to all conf files where this value is hardcoded
STORE_ENTITY_CACHE = 'em_entity_cache'

INDEX_METRICS = 'em_metrics'
INDEX_EVENTS = 'main'
INDEX_META = 'em_meta'

DEFAULT_BATCH_SIZE = 1000
# Need to change limits.conf to update this value
KVSTORE_SINGLE_FETCH_LIMIT = 50000

NOTIFY_WHEN = {
  'IMPROVE': 'improve',
  'DEGRADE': 'degrade',
  'IMPROVE_OR_DEGRADE': 'improve,degrade',
}

ENTITY_CLASS_TO_ENTITY_TYPE_IDS = {
  'os': 'nix',
  'telegraf': 'nix',
  'perfmon': 'windows',
  'k8s_node': 'k8s_node',
  'k8s_pod': 'k8s_pod',
  'vmware_host': 'vmware_esxi_host',
  'vmware_vm': 'vmware_vm',
  'vmware_cluster': 'vmware_cluster',
  'vmware_vcenter': 'vmware_vcenter',
}

# Default metric used for color by in tile view
DEFAULT_METRIC_FOR_COLOR_BY = _('Availability')

# Endpoint to fetch latest created alerts
LATEST_ALERTS_ENDPOINT = '%s/servicesNS/-/%s/admin/alerts/-?%s'

# Endpoint to fetch metadata about created alert
ALERTS_METADATA_ENDPOINT = '%s/servicesNS/-/%s/saved/searches/%s?%s'

# Endpoint to fetch results via search_id
SEARCH_RESULTS_ENDPOINT = '%s/servicesNS/-/%s/search/jobs/%s/results'

# Regular expression to extract alerting entity and alerting metric
ALERTS_SEARCH_EXTRACTION = r'\(?\"(host|InstanceId)\"=\"(?P<alerting_entity>[^\"]+)\"\)? ' \
    'AND metric_name=\"(?P<metric_name>[^\"]+)\"'

# Regular expression to match routing key, from best practices at
# https://help.victorops.com/knowledge-base/routing-keys/
VICTOROPS_ROUTING_KEY = r'^([a-zA-Z0-9\-_])+$'

# Regular expression to match API key.
# (Only contains lower case letters, numbers, and dashes in between)
# I.E - In the form of a GUID/UUID
VICTOROPS_API_KEY = r'^[a-f0-9]{8}-([a-f0-9]{4}-){3}([a-f0-9]{12})$'

# URL from: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-metadata.html
AWS_ENV_CHECK_URL = 'http://169.254.169.254/latest/meta-data/'

# SII deployment environment types
DEPLOYMENT_EC2 = 'ec2'
DEPLOYMENT_NON_EC2 = 'non-ec2'

# We skip discovery of these dims because including them causes a parse error due to a bug in the mcatalog command.
# SII-3766: added 'status' to this list
DIM_KEYS_BLACKLIST = ['from', 'by', 'where', 'groupby', 'status']

KUBERNETES_COLLECTORS = ['k8s_node', 'k8s_pod']

# Key to represent entity status
STATUS_KEYS = ['state', 'status']
