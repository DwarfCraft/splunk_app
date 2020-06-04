"""
(C) 2019 Splunk Inc. All rights reserved.

Modular input which periodically goes and deletes old alerts from KV Store
"""

import sys
from spacebridgeapp.util import py23
from splunk.clilib.bundle_paths import make_splunkhome_path

from solnlib import modular_input
from spacebridgeapp.util.splunk_utils.common import modular_input_should_run
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.util.alerts_ttl_utility import AlertsTtlUtility


class AlertsTTLModularInput(modular_input.ModularInput):
    title = 'Splunk Cloud Gateway Mobile Alerts TTL'
    description = 'Cleans up storage of old mobile alerts'
    app = 'Splunk App Cloud Gateway'
    name = 'splunkappcloudgateway'
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    logger = setup_logging(constants.SPACEBRIDGE_APP_NAME + '.log', 'alerts_ttl_modular_input.app')
    ttl_days = "ttl_days"
    input_config_key = "alerts_ttl_modular_input://default"

    def construct_ttl_list(self, ttl_days):
        return []

    def do_run(self, input_config):
        """
        Executes the modular input using the input config which specifies TTL for alerts
        """
        if not modular_input_should_run(self.session_key, logger=self.logger):
            self.logger.debug("Modular input will not run on this node.")
            return

        self.logger.info("Running Alerts TTL modular input with input=%s" % str(input_config))
        alerts_ttl_utility = AlertsTtlUtility(self.session_key,
                                              float(input_config[self.input_config_key][self.ttl_days]))
        alerts_ttl_utility.run()

    def extra_arguments(self):
        """
        Override extra_arguments list for modular_input scheme
        :return:
        """
        return [{'name': 'ttl_days',
                 'title': 'TTL in Days',
                 'description': 'Alert ttl specified in days'}]


if __name__ == "__main__":
    worker = AlertsTTLModularInput()
    worker.execute()
