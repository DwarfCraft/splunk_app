"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for the NLPserver-to-spacebridge registration process. It
gets an auth token from the NLP server and calls the splapp registration endpoints.
"""

import sys
import json
import base64
import uuid
import requests
import splunk.rest as rest
import splunk.entity as en
from splunk.persistconn.application import PersistentServerConnectionApplication
from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))

from cloudgateway.registration import pair_device
from cloudgateway.device import DeviceInfo
from spacebridgeapp.rest.config.app import retrieve_state_of_app
from spacebridgeapp.rest.config.deployment_info import get_deployment_friendly_name
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.rest.base_endpoint import BaseRestHandler
from cloudgateway.splunk.encryption import SplunkEncryptionContext
from spacebridgeapp.rest.services.spacebridge_service import delete_device_from_spacebridge
from spacebridgeapp.rest.services.kvstore_service import KVStoreCollectionAccessObject as KvStore
from spacebridgeapp.rest.config.app import set_state_of_app
from spacebridgeapp.rest.services.splunk_service import get_all_users
import spacebridgeapp.nlp.rest.utils as nlp_utils
from spacebridgeapp.util.constants import NOBODY
from spacebridgeapp.util.config import cloudgateway_config as config
from cloudgateway.auth import SimpleUserCredentials

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + ".log", "nlp_rest_registration_confirmation")

QUERY_LABEL = 'query'

AUTH_CODE_LABEL = 'auth_code'
DEVICE_NAME_LABEL = 'device_name'
DEVICE_ID_LABEL = 'device_id'
DEVICE_TYPE_LABEL = 'device_type'
APP_ID_LABEL = 'app_id'
NLP_APP_ID = 'com.splunk.nlp.cloud'
KVSTORE_TEMPORARY_ID_LABEL = 'temp_key'
NLP_DEVICE_NAME_PREFIX = 'nlp-b3t4-'
DEFAULT_NLP_SERVER = "https://localhost:9999"

DEVICE_REGISTRATION_ATTRS = ['device_name', 'device_type', 'device_id', 'app_id']
DEVICE_PUBLIC_KEYS_ATTRS = ['encrypt_public_key', 'sign_public_key']

class NlpRegistrationConfirmationHandler(BaseRestHandler, PersistentServerConnectionApplication):
    """
    Main class for handling REST Registration endpoint. Subclasses the spacebridge_app
    BaseRestHandler. This multiple inheritance is an unfortunate neccesity based on the way
    Splunk searches for PersistentServerConnectionApplications
    """

    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)

    def post(self, request):
        user = request['session']['user']
        authtoken = request['session']['authtoken']
        system_authtoken = request['system_authtoken']
        body = json.loads(request['payload'])
        return handle_confirmation(user, authtoken, system_authtoken, body)

def get_nlp_auth_url(user, system_authtoken):
    try:
        ent = en.getEntity(["configs", "conf-nlp"],
                           "config",
                           namespace=constants.SPACEBRIDGE_APP_NAME, owner=user,
                           sessionKey=system_authtoken)
        if "nlp_auth_server" in ent and nlp_utils.check_https(ent["nlp_auth_server"]) and "nlp_auth_server_api_version" in ent:
            return  ent["nlp_auth_server"] + "/nlp/auth/" + ent["nlp_auth_server_api_version"]
    except Exception as ex:
        LOGGER.exception('Unable to get NLP server configuration, using default NLP server={}: {}'
                    .format(DEFAULT_NLP_SERVER, ex))

    return DEFAULT_NLP_SERVER

def handle_confirmation(user, authtoken, system_authtoken, body):
    """
    Handler for the NLP service registration call. This function:
        1. Gets an auth code from the NLP server
        2. Call the reqistration/query endpoint to get a temp key
        3. Use that temp key to register (registration/confirmation)

    :param auth_code: User-entered authorization code to be returned to Spacebridge
    :param user: User running the query
    :param body: Parsed JSON body of the incoming POST request
    :param system_authtoken: System-level access token for writing to the kvstore
    :return: Success message
    """

    if nlp_utils.is_nlp_enabled(system_authtoken, user):
        return {
            'payload': 'NLP feature flag is not enabled',
            'status': 500,
        }

    LOGGER.info('Received NLP service registration request by user={}'.format(user))
    device_name = NLP_DEVICE_NAME_PREFIX + str(uuid.uuid4())
    nlp_auth_url = get_nlp_auth_url(user, system_authtoken)
    deployment_info = nlp_utils.get_deployment_info(authtoken)
    deployment_id = deployment_info['deployment_id']

    auth_code_url =  '{}/registration/authcode/{}'.format(nlp_auth_url, deployment_id)

    LOGGER.info('authCode URL={}'.format(auth_code_url))
    proxies = config.get_proxies()
    r = requests.get(auth_code_url,
                            proxies=proxies,
                            verify=True)
    if not r.status_code == requests.codes.ok:
        return {
            'payload': 'Failed to get Auth Code',
            'status': 500,
        }

    auth_code = r.content

    # enable NLP APP
    set_state_of_app(constants.NLP, authtoken, system_authtoken, True)

    delete_all_nlp_devices(authtoken, system_authtoken)
    params = {AUTH_CODE_LABEL: auth_code, DEVICE_NAME_LABEL: device_name}
    serverResponse, serverContent = rest.simpleRequest("registration/query", getargs=params,
                                                       sessionKey=authtoken)
    reg_query_result = json.loads(serverContent)
    if not KVSTORE_TEMPORARY_ID_LABEL in reg_query_result:
        return {
            'payload': 'Invalid registration data',
            'status': 500,
        }
    temp_key = reg_query_result[KVSTORE_TEMPORARY_ID_LABEL]

    LOGGER.info('NLP service registration confirmed, device_name=\"{}\" temp_key=\"{}\"'
                .format(device_name, temp_key))
    return  register_device(auth_code, user, system_authtoken, temp_key)

def delete_all_nlp_devices(authtoken, system_authtoken):
    """
    Removes all devices of a given type from all users in the kvstore
    """
    users = get_all_users(authtoken) + [NOBODY]
    for user in users:
        delete_all_nlp_devices_of_type_for_user(user, authtoken, system_authtoken)


def delete_all_nlp_devices_of_type_for_user(user, authtoken, system_authtoken):
    """
    Removes all devices of a given type from a single user in the kvstore
    """
    kvstore = KvStore(constants.REGISTERED_DEVICES_COLLECTION_NAME, authtoken, owner=user)
    r, devices = kvstore.get_all_items()
    devices = json.loads(devices)
    kvstore.delete_items_by_query({APP_ID_LABEL: NLP_APP_ID})

    for device in devices:
        if APP_ID_LABEL in device and device[APP_ID_LABEL] == NLP_APP_ID:
            delete_device_from_spacebridge(device['device_id'], system_authtoken)

def register_device(auth_code, user, system_authtoken, temp_key):
    """
    Handler for the final DevicePairingConfirmationRequest call. This function:
        2. Retrieves temporary record from the kvstore
        3. Checks if app_type has been disabled since registration
        4. Makes the DevicePairingConfirmationRequest request to the server
        5. Creates a new permanent record for the device in the kvstore
        6. Deletes the temporary kvstore record

    :param auth_code: User-entered authorization code to be returned to Spacebridge
    :param body: Parsed JSON body of the incoming POST request
    :param kvstore_unconfirmed: Access object for the temporary registration kvstore
    :param system_authtoken: System-level access token for writing to the kvstore
    :return: Success message
    """

    kvstore_temp = KvStore(constants.UNCONFIRMED_DEVICES_COLLECTION_NAME, system_authtoken, owner=user)
    encryption_context = SplunkEncryptionContext(system_authtoken, constants.SPACEBRIDGE_APP_NAME)

    LOGGER.info('Received new registration confirmation request by user=%s' % (user))

    # Retrieves temporary record from the kvstore
    r, temp_record = kvstore_temp.get_item_by_key(temp_key)
    temp_record = json.loads(temp_record)

    device_id = temp_record[DEVICE_ID_LABEL]
    device_id_raw = base64.b64decode(device_id)

    device_registration = {'_key': base64.urlsafe_b64encode(device_id_raw)}
    device_public_keys = {'_key': base64.urlsafe_b64encode(device_id_raw)}

    for k in temp_record.keys():
        if k in DEVICE_REGISTRATION_ATTRS:
            device_registration[k] = temp_record[k]
        if k in DEVICE_PUBLIC_KEYS_ATTRS:
            device_public_keys[k] = temp_record[k]

    # Checks if app_type has been disabled since registration
    app_name = temp_record[DEVICE_TYPE_LABEL]

    if not retrieve_state_of_app(app_name, system_authtoken):
        disabled_message = 'Registration Error: Application type app_name="%s" is disabled' % app_name
        LOGGER.info(disabled_message)
        return {
            'payload': {
                'message': disabled_message,
                'app_name': app_name,
            },
            'status': 422,
        }

    device_encryption_info = DeviceInfo(
        base64.b64decode(temp_record['encrypt_public_key']),
        base64.b64decode(temp_record['sign_public_key']),
        base64.b64decode(temp_record['device_id']),
        "NA",
        app_id=temp_record['app_id'],
        app_name=temp_record['device_type']
    )

    deployment_friendly_name = get_deployment_friendly_name(system_authtoken)
    pair_device(auth_code, SimpleUserCredentials("dummy", "dummy"), device_encryption_info, encryption_context,
                server_name=deployment_friendly_name, config=config)

    # Creates a new permanent record for the device in the kvstore
    kvstore_user = KvStore(constants.REGISTERED_DEVICES_COLLECTION_NAME, system_authtoken, owner=user)
    kvstore_user.insert_single_item(device_registration)

    # Adds the user to the list of users with registered devices, if not already there
    kvstore_users = KvStore(constants.REGISTERED_USERS_COLLECTION_NAME, system_authtoken)
    kvstore_users.insert_or_update_item_containing_key({'_key': user})

    kvstore_nobody = KvStore(constants.DEVICE_PUBLIC_KEYS_COLLECTION_NAME, system_authtoken)
    kvstore_nobody.insert_single_item(device_public_keys)

    # Deletes the temporary kvstore record
    kvstore_temp.delete_item_by_key(temp_key)

    LOGGER.info('Device registration confirmed. Device with device_name=\"%s\" was recorded in the kvstore.' %
                temp_record[DEVICE_NAME_LABEL])

    return {
        'payload': 'Device registration successful',
        'status': 201,
    }
