"""
(C) 2019 Splunk Inc. All rights reserved.

Modular Input for refreshing the list of registered users
"""

import warnings

warnings.filterwarnings('ignore', '.*service_identity.*', UserWarning)

import sys
import os
from splunk.clilib.bundle_paths import make_splunkhome_path
from spacebridgeapp.util import py23, constants

os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

from solnlib import modular_input
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.splunk_utils.common import modular_input_should_run
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from spacebridgeapp.users.registered_users_sync import RegisteredUsersSync
from spacebridgeapp.rest.services.splunk_service import get_splunk_auth_type


class RegisteredUsersListModularInput(modular_input.ModularInput):
    title = 'Splunk Cloud Gateway Registered Users List'
    description = 'Sync the list of registered gateway users'
    app = 'Splunk App Cloud Gateway'
    name = 'splunkappcloudgateway'
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    logger = setup_logging(SPACEBRIDGE_APP_NAME + '.log', 'registered_users_list_modular_input.app')
    input_config_key = "registered_users_list_modular_input://default"

    def do_run(self, input_config):
        """
        Executes the modular input
        :param input_config:
        :return:
        """
        if not modular_input_should_run(self.session_key, logger=self.logger):
            self.logger.debug("Modular input will not run on this node.")
            return

        if get_splunk_auth_type(authtoken=self.session_key) == constants.SAML:
            self.logger.debug("Registered Users List modular input should not run on SAML environment")
            return

        self.logger.info("Running Registered Users List modular input on search captain node")
        registered_users_sync = RegisteredUsersSync(self.session_key)

        try:
            registered_users_sync.run()
        except:
            self.logger.exception("Failure encountered while running Registered Users List sync")

if __name__ == "__main__":
    worker = RegisteredUsersListModularInput()
    worker.execute()
