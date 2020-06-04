"""
(C) 2019 Splunk Inc. All rights reserved.

Modular input for the Spacebridge app which brings up
a web socket server to talk to Spacebridge
"""

# Suppress warnings to pass AppInspect when calling --scheme
import warnings
import logging
from spacebridgeapp.util import py23
from spacebridgeapp.util.shard import default_shard_id

py23.suppress_insecure_https_warnings()
warnings.filterwarnings('ignore', '.*service_identity.*', UserWarning)

import sys
import os
import requests
from splunk.clilib.bundle_paths import make_splunkhome_path

os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'


from cloudgateway.websocket import CloudGatewayWsClient, WebsocketMode
from cloudgateway.private.sodium_client import SodiumClient
from cloudgateway.splunk.encryption import SplunkEncryptionContext
from solnlib import modular_input
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.rest.clients.async_client_factory import AsyncClientFactory
from spacebridgeapp.messages.message_handler import CloudgatewayMessageHandler
from spacebridgeapp.util import constants
from spacebridgeapp.util.config import cloudgateway_config as config
from spacebridgeapp.rest.config.deployment_info import ensure_deployment_friendly_name
from spacebridgeapp.rest.load_balancer_verification import get_uri
from cloudgateway.splunk.auth import SplunkAuthHeader


class SpacebridgeModularInput(modular_input.ModularInput):
    """ Main entry path for launching the Spacebridge Application
    Modular Input
    Arguments:
        modular_input {[type]} -- [description]
    """
    title = 'Splunk Cloud Gateway'
    description = 'Initializes the Splunk Cloud Gateway application to talk to mobile clients over websockets'
    app = 'Splunk App Cloud Gateway'
    name = 'splunkappcloudgateway'
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    health_check_rerun_seconds = 60
    logger = setup_logging(constants.SPACEBRIDGE_APP_NAME + '_modular_input.log', 'cloudgateway_modular_input.app')

    def do_run(self, input_config):
        """ Spins up a websocket connection Spacebridge and begins
        the reactor loops
        """
        shard_id = default_shard_id()

        self.logger.info("Starting libsodium child process")
        sodium_logger = self.logger.getChild('sodium_client')
        sodium_logger.setLevel(logging.WARN)

        sodium_client = SodiumClient(sodium_logger)
        encryption_context = SplunkEncryptionContext(self.session_key,
                                                     constants.SPACEBRIDGE_APP_NAME,
                                                     sodium_client)

        self.logger.info("Running Splunk Cloud Gateway modular input on search head, shard_id=%s", shard_id)

        # Fetch load balancer address if configured, otherwise use default URI
        try:
            uri = get_uri(self.session_key)
            self.logger.debug("Successfully verified load_balancer_address={}".format(uri))
        except Exception as e:
            self.logger.exception("Failed to verify load_balancer_address. {}".format(e))

        if not uri:
            return

        try:
            ensure_deployment_friendly_name(self.session_key)
            async_client_factory = AsyncClientFactory(uri)
            cloudgateway_message_handler = CloudgatewayMessageHandler(SplunkAuthHeader(self.session_key),
                                                                      logger=self.logger,
                                                                      encryption_context=encryption_context,
                                                                      async_client_factory=async_client_factory,
                                                                      shard_id=shard_id)

            client = CloudGatewayWsClient(encryption_context, message_handler=cloudgateway_message_handler,
                                          mode=WebsocketMode.ASYNC,
                                          logger=self.logger,
                                          config=config,
                                          shard_id=shard_id)

            client.connect()
        except Exception as e:
            self.logger.exception("Exception connecting to cloud gateway={0}".format(e))


if __name__ == "__main__":
    worker = SpacebridgeModularInput()
    worker.execute()
