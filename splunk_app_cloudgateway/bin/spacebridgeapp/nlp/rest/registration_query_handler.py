"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for the query part of the NLPserver-to-spacebridge registration
process. It checks if a device user has the Splunk splunk_nlp_service role.
"""

import sys
import json
import splunk.rest as rest
from splunk.persistconn.application import PersistentServerConnectionApplication
from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.rest.base_endpoint import BaseRestHandler

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + ".log", "nlp_rest_registration_query")

NLP_SERVICE_ACCOUNT_ROLE = "splunk_nlp_service"

DEVICE_NAME_LABEL = 'device_name'
DEVICE_ID_LABEL = 'device_id'
DEVICE_KEY_LABEL = '_key'
DEVICE_TYPE = 'device_type'
REGISTERED_LABEL = 'is_registered'

class NlpRegistrationQueryHandler(BaseRestHandler, PersistentServerConnectionApplication):
    """
    Main class for handling REST Registration endpoint. Subclasses the spacebridge_app
    BaseRestHandler. This multiple inheritance is an unfortunate neccesity based on the way
    Splunk searches for PersistentServerConnectionApplications
    """

    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)

    def get(self, request):
        system_authtoken = request['system_authtoken']
        return handle_query(system_authtoken)

def handle_query(system_authtoken):
    """
    Handler for checking if a device with splunk_nlp_service role is registered. This function
    checks if a user with "splunk_nlp_service" role has registered a device 
    :param user: User running the query
    :return: Registration status of the nlp service 
    """
    is_registered = False
    device_id = ""
    device_key = ""
    device_name = ""
    device_type = ""
    serverResponse, serverContent = rest.simpleRequest("kvstore/users_devices",
                                                       sessionKey=system_authtoken, rawResult=True)
    user_devices = json.loads(serverContent)
    for device in user_devices:
       if DEVICE_TYPE in device and device[DEVICE_TYPE] == constants.NLP:
          is_registered = True
          device_name = device[DEVICE_NAME_LABEL]
          device_id = device[DEVICE_ID_LABEL]
          device_key = device[DEVICE_KEY_LABEL]
          device_type = device[DEVICE_TYPE]
          break

    return {
        'payload': {
            REGISTERED_LABEL  : is_registered,
            DEVICE_ID_LABEL   : device_id,
            DEVICE_KEY_LABEL  : device_key,
            DEVICE_NAME_LABEL : device_name,
            DEVICE_TYPE       : device_type
        },
        'status': 200,
    }
