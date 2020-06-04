"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for the first part of  Spacebridge registration process: validating an auth code
"""

import sys
import json
from splunk.persistconn.application import PersistentServerConnectionApplication
from splunk.clilib.bundle_paths import make_splunkhome_path


sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from cloudgateway.splunk.encryption import SplunkEncryptionContext
from cloudgateway.private.sodium_client import SodiumClient
from cloudgateway.registration import authenticate_code


from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, UNCONFIRMED_DEVICES_COLLECTION_NAME, ADMIN_ALL_OBJECTS, DRONE_MODE
from spacebridgeapp.rest.base_endpoint import BaseRestHandler
from spacebridgeapp.rest.services.kvstore_service import KVStoreCollectionAccessObject as KvStore
from spacebridgeapp.rest.services.splunk_service import user_is_administrator
from spacebridgeapp.rest.util.helper import extract_parameter
from spacebridgeapp.rest.util import errors as Errors
from spacebridgeapp.rest.config.app import retrieve_state_of_app
from spacebridgeapp.rest.devices.user_devices import get_devices_for_user
from spacebridgeapp.rest.services.splunk_service import has_admin_all_objects
from spacebridgeapp.util.config import cloudgateway_config as config
from spacebridgeapp.util.app_info import resolve_app_name
from twisted.web import http

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + ".log", "rest_registration_query")

QUERY_LABEL = 'query'
AUTH_CODE_LABEL = 'auth_code'
DEVICE_NAME_LABEL = 'device_name'
DEVICE_ID_LABEL = 'device_id'
APP_TYPE_LABEL = 'app_type'
ENCRYPT_PUBLIC_KEY_LABEL = 'encrypt_public_key'
SIGN_PUBLIC_KEY_LABEL = 'sign_public_key'


class ValidateAuthCodeHandler(BaseRestHandler, PersistentServerConnectionApplication):
    """
    Main class for handling REST Registration endpoint. Subclasses the spacebridge_app
    BaseRestHandler. This multiple inheritance is an unfortunate neccesity based on the way
    Splunk searches for PersistentServerConnectionApplications
    """

    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)

    def get(self, request):
        auth_code = extract_parameter(request['query'], AUTH_CODE_LABEL, QUERY_LABEL)
        device_name = extract_parameter(request['query'], DEVICE_NAME_LABEL, QUERY_LABEL)
        user = request['session']['user']
        system_authtoken = request['system_authtoken']
        return handle_query(auth_code, device_name, user, system_authtoken)


def handle_query(auth_code, device_name, user, system_authtoken):
    """
    Handler for the initial AuthenticationQueryRequest call. This function:
        1. Makes the AuthenticationQueryRequest request to the server
        2. Checks if app_type has been disabled
        3. Stores a temporary record in the kvstore

    :param auth_code: User-entered authorization code to be returned to Spacebridge
    :param device_name: Name of the new device
    :return: Confirmation code to be displayed to user, and id of temporary kvstore record to be returned later
    """

    LOGGER.info('Received new registration query request by user=%s' % user)

    # Makes the AuthenticationQueryRequest request to the server
    sodium_client = SodiumClient(LOGGER.getChild('sodium_client'))
    encryption_context = SplunkEncryptionContext(system_authtoken, SPACEBRIDGE_APP_NAME, sodium_client)
    client_device_info = authenticate_code(auth_code, encryption_context, resolve_app_name, config=config)
    app_name = client_device_info.app_name
    app_id = client_device_info.app_id

    LOGGER.info("client_device_info={}".format(client_device_info))

    user_devices = get_devices_for_user(user, system_authtoken)
    LOGGER.info("user_devices=%s" % user_devices)

    if any(device[DEVICE_NAME_LABEL] == device_name and device['device_type'] == app_name for device in user_devices):
        err_msg = ('Registration Error: user={} device_name={} of app_type={} already exists'
                   .format(user, device_name, app_name))
        LOGGER.info(err_msg)
        raise Errors.SpacebridgeRestError(err_msg, http.CONFLICT)

    # Checks if app_type has been disabled
    if not retrieve_state_of_app(app_name, system_authtoken):
        disabled_message = 'Registration Error: Application type app_name="{}" is disabled'.format(app_name)
        LOGGER.info(disabled_message)
        return {
            'payload': {
                'message': disabled_message,
                'is_admin': user_is_administrator(user, system_authtoken),
                'app_name': app_name,
            },
            'status': 422,
        }


    # Stores a temporary record in the kvstore
    kvstore_unconfirmed = KvStore(UNCONFIRMED_DEVICES_COLLECTION_NAME, system_authtoken, owner=user)
    kvstore_payload = client_device_info.to_json()
    kvstore_payload['device_name'] = device_name
    kvstore_payload['device_type'] = app_name
    kvstore_payload['app_id'] = app_id
    _, content = kvstore_unconfirmed.insert_single_item(kvstore_payload)


    return {
        'payload': {
            'temp_key': json.loads(content)['_key'],
            'conf_code': client_device_info.confirmation_code
        },
        'status': http.OK,
    }
