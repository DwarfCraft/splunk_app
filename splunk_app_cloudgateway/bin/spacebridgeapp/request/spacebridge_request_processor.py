"""
(C) 2019 Splunk Inc. All rights reserved.
"""

import json
from base64 import urlsafe_b64encode, b64encode, b64decode
from spacebridgeapp.util import py23
from cloudgateway.splunk.auth import SimpleUserCredentials, SplunkJWTMDMCredentials
from cloudgateway.mdm import CloudgatewayMdmRegistrationError, handle_mdm_authentication_request, \
    ServerRegistrationContext
from twisted.web import http
from twisted.internet import defer
from spacebridgeapp.util import constants
from spacebridgeapp.versioning import app_version
from spacebridgeapp.util.app_info import get_app_platform, resolve_app_name
from spacebridgeapp.util.time_utils import get_current_date
from spacebridgeapp.util.config import cloudgateway_config as config
from spacebridgeapp.logging import setup_logging

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_spacebridge_request_processor.log",
                       "spacebridge_request_processor")


@defer.inlineCallbacks
def _find_owner(auth_header, device_id, all_users, async_kvstore_client):
    """

    :param auth_header: A system auth header
    :param device_id: a url safe base64 encoded device id (same encoding as register device _key)
    :param all_users:  an array of strings indicating all the users to include in the device search
    :param async_kvstore_client:
    :return: the id of the user if a matching device is found, False otherwise
    """
    LOGGER.info("All users=%s" % all_users)

    for user in all_users:
        response = yield async_kvstore_client.async_kvstore_get_request(
            constants.REGISTERED_DEVICES_COLLECTION_NAME, auth_header=auth_header, owner=user, key_id=device_id)

        if response.code == http.OK:
            defer.returnValue(user)

    defer.returnValue(False)


@defer.inlineCallbacks
def unregister_device(auth_header, unregister_event, async_splunk_client, async_kvstore_client):
    """
    :param auth_header: A system auth header
    :param unregister_event: A protobuf spacebridge unregister event
    :param async_splunk_client:
    :param async_kvstore_client:
    :return: True if the device was found and deleted, False otherwise
    """
    event_device_id = py23.urlsafe_b64encode_to_str(unregister_event.deviceId)

    (http_code, all_users) = yield async_splunk_client.async_get_all_users(auth_header)

    user = None

    if http_code == http.OK:
        user = yield _find_owner(auth_header, event_device_id, all_users, async_kvstore_client)
    else:
        LOGGER.warn("Failed to list all users, status=%s" % http_code)

    found = False

    if user:
        yield async_kvstore_client.async_kvstore_delete_request(constants.REGISTERED_DEVICES_COLLECTION_NAME,
                                                                auth_header=auth_header,
                                                                key_id=event_device_id,
                                                                owner=user)
        yield async_kvstore_client.async_kvstore_delete_request(constants.DEVICE_PUBLIC_KEYS_COLLECTION_NAME,
                                                                auth_header=auth_header,
                                                                key_id=event_device_id,
                                                                owner=constants.NOBODY)
        devices = yield async_kvstore_client.async_kvstore_get_request(constants.REGISTERED_DEVICES_COLLECTION_NAME,
                                                                       auth_header=auth_header,
                                                                       owner=user)
        devices_json = yield devices.json()
        if len(devices_json) <= 0:
            LOGGER.info("User={} has no remaining registered devices, removing user from registered users".format(user))
            yield async_kvstore_client.async_kvstore_delete_request(constants.REGISTERED_USERS_COLLECTION_NAME,
                                                                    auth_header=auth_header,
                                                                    key_id=user)
        found = True

    defer.returnValue(found)


@defer.inlineCallbacks
def mdm_authentication_request(auth_header, mdm_auth_request, async_client_factory, encryption_context, request_id):
    """

    :type async_client_factory: AsyncClientFactory
    """
    LOGGER.info("starting mdm_authentication_request, request_id={}".format(request_id))
    try:
        mdm_registration_ctx = CloudgatewayMdmRegistrationContext(async_client_factory.splunk_client(),
                                                                  async_client_factory.kvstore_client(),
                                                                  auth_header)

        result = yield handle_mdm_authentication_request(mdm_auth_request, encryption_context, mdm_registration_ctx,
                                                         LOGGER, config, request_id)
        LOGGER.info("completed mdm_authentication_request, request_id={}".format(request_id))
        defer.returnValue(result)
    except Exception as e:
        LOGGER.exception("Unexpected exception occured during mdm_authentication_request={}, request_id={}"
                         .format(e, request_id))


class CloudgatewayMdmRegistrationContext(ServerRegistrationContext):
    """
    Base class for Cloudgateway MDM registration.
    """
    # pycharm type annotations
    async_kvstore_client = None  # type: AsyncKvStoreClient
    async_splunk_client = None  # type: AsyncSplunkClient

    def __init__(self, async_splunk_client, async_kvstore_client, system_auth_header):
        """
        :param async_splunk_client (AsyncSplunkClient)
        :param async_kvstore_client:(AsyncKvStoreClient)
        :param system_auth_header: (AuthHeader)
        """
        self.async_splunk_client = async_splunk_client
        self.async_kvstore_client = async_kvstore_client
        self.system_auth_header = system_auth_header

        ServerRegistrationContext.__init__(self, config)

    @defer.inlineCallbacks
    def validate_username_password(self, username, password):
        """
        Validate username and password against splunk
        :param username (String)
        :param password (String)
        :return (Boolean)
        :raises (CloudgatewayMdmRegistrationError)
        """
        response = yield self.async_splunk_client.async_get_splunk_cookie(username, password)
        if response.code == http.OK:
            defer.returnValue(True)

        message = yield response.text()
        LOGGER.info("valid_session_token=false with message={}, status_code={}".format(message, response.code))

        raise CloudgatewayMdmRegistrationError(CloudgatewayMdmRegistrationError.ErrorType.INVALID_CREDENTIALS_ERROR,
                                               "Failed to authenticate session token with error={}, status_code={}"
                                               .format(message, response.code))

    @defer.inlineCallbacks
    def validate_app_enabled(self, device_info):
        """
        Validate whether the app corresponding to the device info object is enabled
        :type device_info: (DeviceInfo)
        :raises CloudgatewayMdmRegistrationError
        """
        app_name = resolve_app_name(device_info.app_id)
        r = yield self.async_splunk_client.async_get_app_state(self.system_auth_header, app_name)

        if r.code == http.OK:
            message = yield r.json()
            if message[app_name]:
                defer.returnValue(True)

            raise CloudgatewayMdmRegistrationError(
                CloudgatewayMdmRegistrationError.ErrorType.APPLICATION_DISABLED_ERROR,
                "Your application is currently disabled. Please ask an admin to " +
                "enabled it from the Splunk Cloudgateway UI")

        message = yield r.text()
        raise CloudgatewayMdmRegistrationError(CloudgatewayMdmRegistrationError.ErrorType.UNKNOWN_ERROR,
                                               message)

    @defer.inlineCallbacks
    def validate(self, username, password, device_info):
        """
        Validates whether the supplied username and password are correct against splunk and also validates whether
        app that the user is trying to register is enabled.
        :param username:
        :param password:
        :param device_info:
        :return (boolean)
        :raises CloudgatewayMdmRegistrationError
        """
        LOGGER.debug("validating whether app is enabled")
        yield self.validate_app_enabled(device_info)
        LOGGER.debug("app is enabled. Checking username and password")
        yield self.validate_username_password(username, password)
        LOGGER.debug("completed mdm validation")
        defer.returnValue(True)

    @defer.inlineCallbacks
    def create_session_token(self, username, password):  # pylint: disable=no-self-use
        """
        Create a session token given a username and password.
        :param username (string)
        :param password (string)
        :return (string): session token string
        """
        try:
            user_auth = SplunkJWTMDMCredentials(username, password=password)
            yield user_auth.load_jwt_token(self.system_auth_header)
            LOGGER.info("Successfully fetched jwt token")
        except Exception as e:
            LOGGER.info("Failed to fetch jwt token with message={}. Using basic session token instead.".format(e))
            user_auth = SimpleUserCredentials(username, password)
        defer.returnValue(user_auth.get_credentials())

    def get_server_version(self):  # pylint: disable=no-self-use
        """
        :return (string) splapp version
        """
        return str(app_version())

    @defer.inlineCallbacks
    def get_deployment_name(self):
        """
        Get deployment name
        :return:
        """
        r = yield self.async_kvstore_client.async_kvstore_get_request(
            constants.META_COLLECTION_NAME,
            self.system_auth_header,
            key_id="deployment_info")

        if r.code == http.OK:
            jsn = yield r.json()
            deployment_name = jsn['friendly_name']
            LOGGER.debug("Retrieved deployment_info={}".format(deployment_name))
            defer.returnValue(deployment_name)

        defer.returnValue("")

    def build_device_name(self, device_info, username):  # pylint: disable=no-self-use
        """
        Device name that will be displayed in the UI.
        :param device_info (DeviceInfo)
        :param username (string)
        :return (string) device name
        """
        return "{}-{}-{}".format(username, get_app_platform(device_info.app_id), get_current_date())

    @defer.inlineCallbacks
    def get_mdm_signing_key(self):
        """
        Get the MDM signing key
        """
        LOGGER.info("Fetching mdm signing key")
        r = yield self.async_splunk_client.async_get_deployment_info(self.system_auth_header)

        if r.code == http.OK:
            jsn = yield r.json()
            mdm_signing_key = jsn[constants.MDM_SIGN_PUBLIC_KEY]
            LOGGER.info("successfully fetched mdm public key={}".format(mdm_signing_key))

            defer.returnValue(b64decode(mdm_signing_key))

        LOGGER.error("Could not fetch mdm signing key with response={}".format(r.code))
        defer.returnValue("")

    @defer.inlineCallbacks
    def persist_device_info(self, device_info, username):
        """
        Write device info to KV Store collections

        :param device_info (DeviceInfo)
        :param username (String)
        :return None
        """
        url_safe_device_id = py23.urlsafe_b64encode_to_str(device_info.device_id)
        device_id = py23.b64encode_to_str(device_info.device_id)

        # Insert into public keys table
        device_public_keys_payload = {
            '_key': url_safe_device_id,
            'encrypt_public_key': py23.b64encode_to_str(device_info.encrypt_public_key),
            'sign_public_key': py23.b64encode_to_str(device_info.sign_public_key)
        }

        registration_payload = {
            '_key': url_safe_device_id,
            'app_id': device_info.app_id,
            'device_type': resolve_app_name(device_info.app_id),
            'device_name': self.build_device_name(device_info, username),
            'user': username,
            'device_id': device_id
        }

        keys_resp = yield self.async_kvstore_client.async_kvstore_post_request(
            constants.DEVICE_PUBLIC_KEYS_COLLECTION_NAME,
            json.dumps(device_public_keys_payload),
            self.system_auth_header)

        keys_resp_code = keys_resp.code
        keys_resp_text = yield keys_resp.text()

        if not (keys_resp_code == http.CREATED or keys_resp_code == http.OK):
            raise CloudgatewayMdmRegistrationError(CloudgatewayMdmRegistrationError.ErrorType.UNKNOWN_ERROR,
                                                   keys_resp_text)

        devices_resp = yield self.async_kvstore_client.async_kvstore_post_request(
            constants.REGISTERED_DEVICES_COLLECTION_NAME,
            json.dumps(registration_payload),
            self.system_auth_header,
            owner=username)

        devices_resp_code = devices_resp.code
        devices_resp_text = yield devices_resp.text()

        if not (devices_resp_code == http.CREATED or devices_resp_code == http.OK):
            raise CloudgatewayMdmRegistrationError(CloudgatewayMdmRegistrationError.ErrorType.UNKNOWN_ERROR,
                                                   devices_resp_text)

        # If this call fails it's not a big deal, it's just an optimization. Modular input which runs every day
        # will pick up this user as having a registered device in any case.

        r = yield self.async_kvstore_client.async_kvstore_post_request(constants.REGISTERED_USERS_COLLECTION_NAME,
                                                                       json.dumps({"_key": username}),
                                                                       self.system_auth_header)

        LOGGER.info("Received response_code={} back on add user to registered users collection".format(r.code))

    def get_server_type(self):  # pylint: disable=no-self-use
        """
        :return (string) splapp app id
        """
        return constants.SPLAPP_APP_ID
