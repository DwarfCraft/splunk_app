# Environment configuration
import em_path_inject  # noqa
from builtins import object
# App specific packages
import em_common
from em_subscription_utils import get_installed_subscriptions


class EmSubscriptionsInterfaceImpl(object):
    def __init__(self, system_session_key):
        self.system_session_key = system_session_key

    def handle_list_subscriptions(self):
        return get_installed_subscriptions(
            server_uri=em_common.get_server_uri(),
            session_key=self.system_session_key)
