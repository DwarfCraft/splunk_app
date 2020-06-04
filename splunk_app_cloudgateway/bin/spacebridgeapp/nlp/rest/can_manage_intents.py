"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for the Spacebridge registration process, including
both the AuthenticationQueryRequest and the DevicePairingConfirmationRequest
"""

import sys
from splunk.persistconn.application import PersistentServerConnectionApplication
from splunk.clilib.bundle_paths import make_splunkhome_path


sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))

from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.rest.base_endpoint import BaseRestHandler
import spacebridgeapp.nlp.rest.utils as nlp_utils

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + ".log", "rest_nlp_can_manage_intents")

NLP_WRITE_CAPABILITY = "nlp_write"

class CanManageIntentsHandler(BaseRestHandler, PersistentServerConnectionApplication):
    """
    Main class for handling REST Can Manage Intents endpoint. Subclasses the spacebridge_app
    BaseRestHandler. This multiple inheritance is an unfortunate neccesity based on the way
    Splunk searches for PersistentServerConnectionApplications
    """

    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)

    def get(self, request):
        user = request['session']['user']
        user_token = request['session']['authtoken']

        return {
            'payload': {
                'can_manage_intents': nlp_utils.user_has_capability(user, user_token, NLP_WRITE_CAPABILITY)
            },
            'status': 200,
        }
