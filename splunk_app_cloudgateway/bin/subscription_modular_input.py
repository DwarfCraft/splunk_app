"""
(C) 2019 Splunk Inc. All rights reserved.

Modular Input for processing publish and subscription process
"""
import warnings
import logging

warnings.filterwarnings('ignore', '.*service_identity.*', UserWarning)

import multiprocessing
import os
from spacebridgeapp.util import py23

py23.suppress_insecure_https_warnings()
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

from cloudgateway.splunk.auth import SplunkAuthHeader
from spacebridgeapp.subscriptions import loader
from spacebridgeapp.subscriptions.process_manager import ProcessManager, JobContext, start_job_using_subprocess, \
    start_job_single_process
from spacebridgeapp.util.shard import default_shard_id
from cloudgateway.private.sodium_client import SodiumClient
from cloudgateway.splunk.encryption import SplunkEncryptionContext
from solnlib import modular_input
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from spacebridgeapp.subscriptions.subscription_manager import SubscriptionManager
from cloudgateway.private.websocket.parent_process_monitor import ParentProcessMonitor
from spacebridgeapp.rest.load_balancer_verification import get_uri
from splunk.clilib.bundle_paths import make_splunkhome_path


class SubscriptionModularInput(modular_input.ModularInput):
    """
    Main entry for processing Search Subscriptions
    """
    title = 'Splunk Cloud Gateway Subscription Processor'
    description = 'Process subscriptions and send visualization data to subscribed devices.'
    app = 'Splunk App Cloud Gateway'
    name = 'splunkappcloudgateway'
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    logger = setup_logging(SPACEBRIDGE_APP_NAME + '_modular_input.log', 'subscription_modular_input.app')

    input_config_key = "subscription_modular_input://default"
    minimum_iteration_time_seconds = "minimum_iteration_time_seconds"
    warn_threshold_seconds = "maximum_iteration_time_warn_threshold_seconds"
    subscription_processor_parallelism = 'subscription_processor_parallelism'

    python_path = make_splunkhome_path(['bin', 'splunk'])
    script_path = make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin', 'subscription_subprocess.py'])
    subprocess_args = ['splunk', 'cmd', 'python', script_path]

    CONFIG_VALUE_NCPU = 'N_CPU'
    CONFIG_VALUE_SINGLE_PROCESS = 1

    def _resolve_parallelism(self, config_value):
        if config_value == self.CONFIG_VALUE_NCPU:
            parallelism = multiprocessing.cpu_count()
        else:
            parallelism = int(config_value)

        if parallelism <= 0:
            raise ValueError('Parallelism must be > 0, found {}'.format(parallelism))

        self.logger.debug("Using search process parallelism=%s", parallelism)
        return parallelism

    def do_run(self, input_config):
        shard_id = default_shard_id()

        self.logger.info("Starting libsodium child process")
        sodium_logger = self.logger.getChild('sodium_client')
        sodium_logger.setLevel(logging.WARN)
        sodium_client = SodiumClient(sodium_logger)
        self.logger.info("Loading encryption context")
        encryption_context = SplunkEncryptionContext(self.session_key, SPACEBRIDGE_APP_NAME, sodium_client)

        self.logger.info("Running Subscription Manager modular input on search head")

        # Fetch load balancer address if configured, otherwise use default URI
        try:
            uri = get_uri(self.session_key)
            self.logger.debug("Successfully verified load_balancer_address={}".format(uri))
        except Exception as e:
            self.logger.exception("Failed to verify load_balancer_address. {}".format(e))

        if not uri:
            return

        try:
            minimum_iteration_time_seconds = float(input_config[self.input_config_key][self.minimum_iteration_time_seconds])
            warn_threshold_seconds = float(input_config[self.input_config_key][self.warn_threshold_seconds])
            subscription_processor_parallelism_str = input_config[self.input_config_key][self.subscription_processor_parallelism]
            subscription_parallelism = self._resolve_parallelism(subscription_processor_parallelism_str)
        except:
            self.logger.exception("Failed to load required configuration values")
            return

        try:
            self.logger.info("Processing subscriptions with parallelism=%s", subscription_parallelism)
            auth_header = SplunkAuthHeader(self.session_key)

            self.logger.debug("Using search processor python=%s, script=%s, args=%s", self.python_path, self.script_path, self.subprocess_args)
            start_job = start_job_using_subprocess(self.python_path, self.subprocess_args)

            if subscription_parallelism == self.CONFIG_VALUE_SINGLE_PROCESS:
                start_job = start_job_single_process(sodium_client, encryption_context)

            process_manager = ProcessManager(subscription_parallelism, start_job)
            job_context = JobContext(auth_header,
                                     uri,
                                     encryption_context.get_encryption_keys().to_json())

            subscription_manager = SubscriptionManager(input_config=input_config,
                                                       encryption_context=encryption_context,
                                                       auth_header=auth_header,
                                                       shard_id=shard_id,
                                                       job_context=job_context,
                                                       search_loader=loader.load_search_bundle,
                                                       parent_process_monitor=ParentProcessMonitor(),
                                                       minimum_iteration_time_seconds=minimum_iteration_time_seconds,
                                                       warn_threshold_seconds=warn_threshold_seconds,
                                                       process_manager=process_manager
                                                       )

            subscription_manager.run()
        except:
            self.logger.exception("Unhandled exception during subscription processing")


if __name__ == "__main__":
    worker = SubscriptionModularInput()
    worker.execute()
