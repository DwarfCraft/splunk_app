"""
(C) 2019 Splunk Inc. All rights reserved.
"""

import json
import sys
import time
import splunk

from splunk.clilib.bundle_paths import make_splunkhome_path
from splunk.persistconn.application import PersistentServerConnectionApplication

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))

from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.rest.util.validation import validate_deployment_name
from spacebridgeapp.rest.base_endpoint import BaseRestHandler
from spacebridgeapp.rest.services.kvstore_service import KVStoreCollectionAccessObject as kvstore
from spacebridgeapp.rest.services.splunk_service import  user_is_administrator
from twisted.web import http


from spacebridgeapp.util.constants import SESSION, USER, AUTHTOKEN, NOBODY, META_COLLECTION_NAME, DEPLOYMENT_INFO, \
    DEPLOYMENT_FRIENDLY_NAME, SYSTEM_AUTHTOKEN, PAYLOAD

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + ".log", "set_deployment_name")


class DeploymentName(BaseRestHandler, PersistentServerConnectionApplication):
    """
    Main class for handling the deployment_name endpoint. Subclasses the spacebridge_app
    BaseRestHandler.
    """

    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)

    def post(self, request):

        user = request[SESSION][USER]
        system_authtoken = request[SYSTEM_AUTHTOKEN]
        payload = json.loads(request[PAYLOAD])

        deployment_name = payload.get('deployment_name', '')
        status_code = http.OK
        error_message = None

        valid_deployment_name = validate_deployment_name(deployment_name)

        if not valid_deployment_name:
            error_message = "Invalid Deployment Name"
            status_code = http.BAD_REQUEST

        # Don't check kvstore if we already have an error
        if error_message:
            return {
                'payload': error_message,
                'status': status_code,
            }

        # Get the kvstore object first because posting overwrites the entire object
        try:
            kvstore_service = kvstore(collection=META_COLLECTION_NAME,
                                      session_key=request[SESSION][AUTHTOKEN],
                                      owner=NOBODY)
            result = json.loads(kvstore_service.get_item_by_key(DEPLOYMENT_INFO)[1])

        except Exception as e:
            # If key not in kvstore
            if hasattr(e, 'statusCode') and e.statusCode == http.NOT_FOUND:
                error_message = 'Could not find deployment info in kvstore'
                error_status = http.NOT_FOUND
            elif hasattr(e, 'statusCode'):
                error_message = e.message
                error_status = e.statusCode
            else:
                error_message = e.message
                error_status = http.BAD_REQUEST

            return {
                'payload': {
                    'message': error_message,
                    'status': error_status
                }
            }

        # Set new deployment name
        result[DEPLOYMENT_FRIENDLY_NAME] = valid_deployment_name

        try:
            kvstore_service.insert_or_update_item_containing_key(result)

        except Exception as e:
            return {
                'payload': {
                    'message': e.message,
                    'status': http.INTERNAL_SERVER_ERROR
                }
            }

        return {
            'payload': valid_deployment_name,
            'status': status_code,
        }

