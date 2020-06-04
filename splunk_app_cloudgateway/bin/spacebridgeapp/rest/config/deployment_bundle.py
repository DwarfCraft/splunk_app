"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for creating and accessing an MDM deployment bundle
"""

import sys
import json
from base64 import b64encode, b64decode
from datetime import datetime
from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23
from twisted.web import http

from spacebridgeapp.logging import setup_logging
from spacebridgeapp.rest.base_endpoint import BaseRestHandler
from spacebridgeapp.rest.services.kvstore_service import KVStoreCollectionAccessObject as kvstore
from spacebridgeapp.rest.services.splunk_service import update_or_create_sensitive_data, fetch_sensitive_data
from spacebridgeapp.rest.services.spacebridge_service import send_mdm_signing_key_to_spacebridge
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, SESSION, AUTHTOKEN, MDM_SIGN_PUBLIC_KEY, \
                                          USER_META_COLLECTION_NAME, USER, MDM_KEYPAIR_GENERATION_TIME, KEY, TIMESTAMP, \
                                          SIGN_PUBLIC_KEY, SIGN_PRIVATE_KEY, CREATED, MDM_SIGN_PRIVATE_KEY

from cloudgateway.private.sodium_client.sodium_client import SodiumClient
from splunk.persistconn.application import PersistentServerConnectionApplication

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + ".log", "deployment_bundle")

class DeploymentBundle(BaseRestHandler, PersistentServerConnectionApplication):
    """
    Main class for handling the deployment bundle endpoint. Subclasses the spacebridge_app
    BaseRestHandler.

    """

    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)
        self.sodium_client = SodiumClient()

    def get(self, request):
        """
        Handler which returns mdm signing public key
        """

        response = {}
        try:
            kvstore_service = kvstore(collection=USER_META_COLLECTION_NAME, session_key=request[SESSION][AUTHTOKEN], owner=request[SESSION][USER])
            result = json.loads(kvstore_service.get_item_by_key(MDM_KEYPAIR_GENERATION_TIME)[1])
            response.update({TIMESTAMP: result[TIMESTAMP]})

        except Exception as e:
            # If key not in kvstore
            if hasattr(e, 'statusCode') and e.statusCode == http.NOT_FOUND:
                return {
                    'payload': {
                        'message': 'Could not find mdm keypair update time in kvstore',
                        'status': http.NOT_FOUND
                    }
                }
            return {
                'payload': {
                    'message': e.message,
                    'status': http.BAD_REQUEST
                }
            }


        try:
            public_key = fetch_sensitive_data(request[SESSION][AUTHTOKEN], MDM_SIGN_PUBLIC_KEY)
            private_key = fetch_sensitive_data(request[SESSION][AUTHTOKEN], MDM_SIGN_PRIVATE_KEY)
            response.update({'sign_public_key': public_key, 'sign_private_key': private_key})
        except Exception as e:
            # If key not in storage/passwords
            if hasattr(e, 'statusCode') and e.statusCode == http.NOT_FOUND:
                return {
                    'payload': {
                        'message': 'Could not find one or both of key={} and key={} in /storage/passwords'
                            .format(MDM_SIGN_PUBLIC_KEY,
                                    MDM_SIGN_PRIVATE_KEY),
                        'status': http.NOT_FOUND
                    }
                }

            return {
                'payload': {
                    'message': e.message,
                    'status': http.BAD_REQUEST
                }
            }

        return {
            'payload': response,
            'status': http.OK
        }

    def post(self, request):
        """
        Handler which generates and returns an mdm keypair
        """

        # generate mdm credentials
        LOGGER.info("Generating MDM Credentials")
        [public_key, private_key] = [b64encode(k) for k in self.sodium_client.sign_generate_keypair()]
        now = int(datetime.now().strftime('%s'))

        response = {}
        response['message'] = []
        status = http.OK

        try:
            # send public signing key to spacebridge
            send_mdm_signing_key_to_spacebridge(request[SESSION][AUTHTOKEN], b64decode(public_key))

        except Exception as e:
            status = http.INTERNAL_SERVER_ERROR
            return {
                'payload': {'failed_save': True, 'message': e.message},
                'status': status,
            }

        # update key generation timestamp
        try:
            kvstore_service = kvstore(collection=USER_META_COLLECTION_NAME, session_key=request[SESSION][AUTHTOKEN], owner=request[SESSION][USER])
            entry = {KEY: MDM_KEYPAIR_GENERATION_TIME, TIMESTAMP: now}
            kvstore_service.insert_or_update_item_containing_key(entry)

        except Exception as e:
            status = http.INTERNAL_SERVER_ERROR
            response['failed_timesave'] = True
            response['message'].append(e.message)

        # store to storage/passwords
        try:
            [_, created_public_key] = update_or_create_sensitive_data(request[SESSION][AUTHTOKEN], MDM_SIGN_PUBLIC_KEY, public_key)

        except Exception as e:
            status = http.INTERNAL_SERVER_ERROR
            response['failed_public_localsave'] = True
            response['message'].append(e.message)

        try:
            [_, created_private_key] = update_or_create_sensitive_data(request[SESSION][AUTHTOKEN], MDM_SIGN_PRIVATE_KEY, private_key)

        except Exception as e:
            status = http.INTERNAL_SERVER_ERROR
            response['failed_private_localsave'] = True
            response['message'].append(e.message)

        # don't pass back the message if we have no errors
        if not response['message']:
            del response['message']

        response[SIGN_PUBLIC_KEY] = public_key
        response[SIGN_PRIVATE_KEY] = private_key
        response[TIMESTAMP] = now

        return {
            'payload': response,
            'status': status,
        }
