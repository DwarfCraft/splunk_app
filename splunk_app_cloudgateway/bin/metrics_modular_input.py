"""
(C) 2019 Splunk Inc. All rights reserved.

Modular input for the Spacebridge app which brings up
a web socket server to talk to Spacebridge
"""

import warnings

warnings.filterwarnings('ignore', '.*service_identity.*', UserWarning)

import sys
import os
import time
from splunk.clilib.bundle_paths import make_splunkhome_path
from spacebridgeapp.util import py23

os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

from solnlib import modular_input
from spacebridgeapp.util.splunk_utils.common import modular_input_should_run
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.metrics.metrics_collector import SpacebridgeaAppMetricsCollector


class MetricsModularInput(modular_input.ModularInput):
    """

    Modular input to periodically collect cloudgateway metrics
    """
    title = 'Splunk Cloud Gateway Metrics Collector'
    description = 'Collects metrics for Splunk Cloud Gateway'
    app = 'Splunk App Cloud Gateway'
    name = 'splunkappcloudgateway'
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    logger = setup_logging(constants.SPACEBRIDGE_APP_NAME + '_metrics.log', 'cloudgateway_metrics.app')

    def do_run(self, input_config):
        """
        Main entry path for input
        """
        self.logger.info("Running cloud gateway metrics modular input")
        if not modular_input_should_run(self.session_key, logger=self.logger):
            self.logger.debug("Modular input will not run on this node.")
            return

        try:
            time.sleep(30)
            collector = SpacebridgeaAppMetricsCollector(self.logger, self.session_key)
            collector.run()
        except:
            self.logger.exception("Exception calculating cloudgateway metrics")


if __name__ == "__main__":
    worker = MetricsModularInput()
    worker.execute()
