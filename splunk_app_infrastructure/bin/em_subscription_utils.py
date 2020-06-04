from service_manager.splunkd.license import LicenseManager

# Define subscriptions required for collectors
# default_collectors are included with base license
# key: License add_ons key (the subscription)
# value: List of EMCollector instance names that require the subscription
COLLECTOR_SUBSCRIPTIONS = {
    'itsi': ['vmware_vcenter', 'vmware_cluster', 'vmware_host', 'vmware_vm'],
    'default_collectors': [
        'aws_cloudwatch_ebs', 'aws_cloudwatch_ec2', 'aws_cloudwatch_elb',
        'k8s_node', 'k8s_pod', 'os', 'perfmon', 'telegraf'
    ]
}


def get_required_susbcriptions_for_feature(feature_name, feature_subscriptions_requirement_map):
    """
    Return a list of subscriptions that allow access to the feature
    """
    subscriptions = []
    for subscription, feature_names in list(feature_subscriptions_requirement_map.items()):
        if feature_name in feature_names:
            subscriptions.append(subscription)
    return subscriptions


def get_installed_subscriptions(server_uri, session_key):
    """
    Return a list of subscriptions extracted from the installed license data
    """
    license_data = get_license_data(server_uri, session_key)
    subscriptions = []
    for entry in license_data.get('entry', []):
        content = entry.get('content', None)
        if content is None:
            continue
        add_ons = content.get('add_ons', None)
        if add_ons is None:
            continue
        # add_ons is a dict of subscription data
        # The keys are what we use to determine access (the subscription)
        for add_on, data in list(add_ons.items()):
            subscriptions.append(add_on)
    return subscriptions


def get_license_data(server_uri, session_key):
    """
    Load the installed license data
    """
    license_manager = LicenseManager(server_uri, session_key, check_local_slave=True)
    return license_manager.load()


def has_collector_subscription(server_uri, session_key, collector_name):
    """
    Get the list of subscriptions that allow access to the collector and check
    if the installed license data contains one of those subscription
    """
    # If collector is included with base license, return early with access
    if collector_name in COLLECTOR_SUBSCRIPTIONS['default_collectors']:
        return True
    # Collector is not included with base license, get valid subscriptions
    feature_subscriptions = get_required_susbcriptions_for_feature(
        feature_name=collector_name,
        feature_subscriptions_requirement_map=COLLECTOR_SUBSCRIPTIONS)
    return has_subscription(server_uri, session_key, feature_subscriptions)


def has_subscription(server_uri, session_key, feature_subscriptions):
    """
    Check if the subscriptions from the installed license data contain at least
    one feature subscription
    """
    installed_subscriptions = get_installed_subscriptions(server_uri, session_key)
    for installed_subscription in installed_subscriptions:
        # If any one of the add_ons/subscription keys is in the feature
        # subscriptions list, access is granted
        if installed_subscription in feature_subscriptions:
            return True
    return False
