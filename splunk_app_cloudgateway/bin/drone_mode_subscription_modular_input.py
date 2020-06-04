"""
(C) 2020 Splunk Inc. All rights reserved.

Modular Input for processing drone mode subscriptions
"""
import sys
import os
import warnings

warnings.filterwarnings('ignore', '.*service_identity.*', UserWarning)


from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'lib']))
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

from cloudgateway.private.sodium_client import SodiumClient
from cloudgateway.splunk.encryption import SplunkEncryptionContext
from cloudgateway.private.websocket.parent_process_monitor import ParentProcessMonitor
from cloudgateway.splunk.cluster.cluster_monitor import ClusterMonitor
from solnlib import modular_input
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.config import cloudgateway_config as config
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from spacebridgeapp.drone_mode.drone_mode_subscription_manager import DroneModeSubscriptionManager
from spacebridgeapp.rest.load_balancer_verification import get_uri
from spacebridgeapp.rest.clients.async_splunk_client import AsyncSplunkClient


class DroneModeSubscriptionModularInput(modular_input.ModularInput):
    """
    Main entry for processing Drone Mode Subscriptions
    """
    title = 'Splunk Cloud Gateway Drone Mode Subscription Processor'
    description = ('Clean up expired subscriptions, and '
                   'send data through Splunk Cloud Gateway send message api')
    app = 'Splunk App Cloud Gateway'
    name = 'splunkappcloudgateway'
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    logger = setup_logging(SPACEBRIDGE_APP_NAME + '_drone_mode_modular_input.log',
                           'drone_mode_modular_input.app')

    def do_run(self, input_config):
        """
        This will spin up a drone mode subscription manager and begins the reactor loop
        :param input_config:
        :return:
        """

        try:
            sodium_client = SodiumClient(self.logger.getChild('sodium_client'))
            encryption_context = SplunkEncryptionContext(self.session_key,
                                                         SPACEBRIDGE_APP_NAME,
                                                         sodium_client)

            self.logger.debug("Running Drone Mode Subscription Manager modular input")

            # Fetch load balancer address if configured, otherwise use default URI
            try:
                uri = get_uri(self.session_key)
                self.logger.debug("Successfully verified load_balancer_address=%s", uri)
            except Exception:
                self.logger.exception("Failed to verify load_balancer_address.")

            if not uri:
                return

            subscription_manager = DroneModeSubscriptionManager(
                input_config=input_config,
                encryption_context=encryption_context,
                session_key=self.session_key,
                async_splunk_client=AsyncSplunkClient(uri),
                parent_process_monitor=ParentProcessMonitor(),
                cluster_monitor=ClusterMonitor(self.logger,
                                               interval=config.get_cluster_monitor_interval())
            )
            subscription_manager.run()

        except Exception as e:
            self.logger.exception('An error occurred running the drone mode subscription modular input')
            raise e


if __name__ == "__main__":
    worker = DroneModeSubscriptionModularInput()
    worker.execute()
