"""
Module to help with MDM based registration
"""
import sys
import os
from cloudgateway import py23

sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib'))

from cloudgateway.private.registration import mdm
from cloudgateway.device import DeviceInfo, make_device_id
from cloudgateway.private.encryption.encryption_handler import sign_verify
from twisted.internet import defer
from spacebridge_protocol import http_pb2, sb_common_pb2
from functools import partial
from cloudgateway.private.clients.async_spacebridge_client import AsyncSpacebridgeClient
from cloudgateway.private.util.twisted_utils import add_error_back
from cloudgateway.private.util import constants

from abc import ABCMeta, abstractmethod
from enum import Enum

MDM_REGISTRATION_VERSION = sb_common_pb2.REGISTRATION_VERSION_1

class CloudgatewayMdmRegistrationError(Exception):
    """
    Exception class to encapsulate exceptions which can occur during MDM registration which will be sent
    back to the client
    """

    class ErrorType(Enum):
        """
        Enum of error types
        """
        INVALID_CREDENTIALS_ERROR = 0
        APPLICATION_DISABLED_ERROR = 1
        UNKNOWN_ERROR = 2

    def __init__(self, error_type, message):
        """
        Args:
            error_type (ErrorType enum): enum specifying the type of error
            message (string): error string describing error
        """
        self.message = message
        self.error_type = error_type

    def to_proto(self):
        """
        Creates a HttpError proto which can be sent back to the client device

        Returns (http_pb2.HttpError proto)
        """
        error = http_pb2.HttpError()
        error.message = self.message

        if self.error_type == self.ErrorType.APPLICATION_DISABLED_ERROR:
            error.code = http_pb2.HttpError.ERROR_APPLICATION_DISABLED

        elif self.error_type == self.ErrorType.INVALID_CREDENTIALS_ERROR:
            error.code = http_pb2.HttpError.ERROR_CREDENTIALS_INVALID

        else:
            error.code = http_pb2.HttpError.ERROR_UNKNOWN
        return error

    def __str__(self):
        return str({'message': self.message, 'type': self.error_type})


@defer.inlineCallbacks
def handle_mdm_authentication_request(mdm_auth_request_proto, encryption_context,
                                      server_context, logger, config, request_id):
    """
    Takes a MDM Auth Request proto, decrypts the encrypted credentials bundle, validates the credentials, persists
    device information to the server and sends cloudgateway a confirmation result message
    Args:
        mdm_auth_request_proto (MdmAuthenticationRequest proto): request from the client to perform MDM registration
        encryption_context (EncryptionContext):
        server_context (ServerContext): object which specifies how mdm registration should be validated and how
            credentials should be persisted to the server
        logger (Logger): logger class to handle logging

    Returns:

    """

    logger.info("Parsing MDM Authentication Request, request_id={}".format(request_id))
    client_credentials = sb_common_pb2.MdmAuthenticationRequest.ClientCredentials()
    client_credentials.ParseFromString(mdm_auth_request_proto.clientCredentials)
    mdm_signature = mdm_auth_request_proto.mdmSignature
    client_signature = mdm_auth_request_proto.clientSignature

    try:
        logger.debug("Validating MDM signature MDM request message, request_id={}".format(request_id))
        mdm_signing_key = yield add_error_back(defer.maybeDeferred(server_context.get_mdm_signing_key),
                                               logger=logger)
        if not sign_verify(encryption_context.sodium_client, mdm_signing_key,
                           mdm_auth_request_proto.clientCredentials, mdm_signature):
            raise CloudgatewayMdmRegistrationError(CloudgatewayMdmRegistrationError.errortype.unknown_error,
                                                   "mdm signature validation failed")

        logger.debug("Validating registration version={}, request_id={}"
                     .format(client_credentials.registrationVersion, request_id))
        if client_credentials.registrationVersion != MDM_REGISTRATION_VERSION:
            raise CloudgatewayMdmRegistrationError(CloudgatewayMdmRegistrationError.ErrorType.UNKNOWN_ERROR,
                                                   "Incompatible Mdm Registration Version. Expected={}"
                                                   .format(MDM_REGISTRATION_VERSION))

        encrypted_credentials_bundle = client_credentials.encryptedCredentialsBundle

        credentials_bundle = mdm.parse_mdm_encrypted_credentials_bundle(encrypted_credentials_bundle,
                                                                        encryption_context)
        client_id = credentials_bundle.registeringAppId
        username = credentials_bundle.username
        password = credentials_bundle.password
        encrypt_public_key = credentials_bundle.publicKeyForEncryption
        sign_public_key = credentials_bundle.publicKeyForSigning
        login_type = credentials_bundle.loginType
        user_session_token = credentials_bundle.sessionToken # JWT session token sent by the client after MDM SAML

        logger.debug("Validating publicKey signature of MDM request message, request_id={}".format(request_id))

        if not sign_verify(encryption_context.sodium_client, sign_public_key, mdm_auth_request_proto.clientCredentials,
                           client_signature):
            raise CloudgatewayMdmRegistrationError(CloudgatewayMdmRegistrationError.ErrorType.UNKNOWN_ERROR,
                                                   "client signature validation failed")

        device_info = DeviceInfo(encrypt_public_key, sign_public_key,
                                 device_id=make_device_id(encryption_context, sign_public_key),
                                 app_id=client_id, client_version="")

        encrypted_session_token = None
        if login_type == constants.SAML:
            encrypted_session_token = user_session_token
        else:
            yield add_error_back(defer.maybeDeferred(server_context.validate, username, password, device_info),
                                 logger=logger)

            logger.debug("Server validated mdm registration request. request_id={}".format(request_id))

            session_token = yield add_error_back(defer.maybeDeferred(server_context.create_session_token, username, password),
                logger=logger)

            encrypted_session_token = encryption_context.secure_session_token(session_token)

        server_version = yield add_error_back(defer.maybeDeferred(server_context.get_server_version),
                                              logger=logger)

        logger.debug("Server returned server_version={}, request_id={}".format(server_version, request_id))

        deployment_name = yield add_error_back(defer.maybeDeferred(server_context.get_deployment_name),
                                               logger=logger)

        logger.debug("Server returned deployment_name={}, request_id={}".format(deployment_name, request_id))

        server_type_id = yield add_error_back(defer.maybeDeferred(server_context.get_server_type),
                                               logger=logger)

        pairing_info = mdm.build_pairing_info(encrypted_session_token, credentials_bundle.username, server_version,
                                              deployment_name, server_type_id)
        confirmation_result = mdm.build_successful_confirmation_result(pairing_info)

        yield add_error_back(defer.maybeDeferred(server_context.persist_device_info, device_info, username),
                             logger=logger)

        logger.info("Successfully persisted device registration information, request_id={}".format(request_id))

    except CloudgatewayMdmRegistrationError as e:
        logger.exception("MDM registration error occurred={}, request_id={}".format(e, request_id))
        confirmation_result = mdm.build_error_confirmation_result(e.to_proto())
    except Exception as e:
        logger.exception("Unexpected error occurred during MDM registration={}, request_id={}".format(e, request_id))
        error = http_pb2.HttpError()
        error.code = http_pb2.HttpError.ERROR_UNKNOWN
        error.message = str(e)
        confirmation_result = mdm.build_error_confirmation_result(error)

    mdm_authentication_confirmation_request = mdm.build_mdm_authentication_confirmation_request(confirmation_result,
                                                                                                encryption_context,
                                                                                                device_info)

    r = yield mdm.async_send_confirmation_result(mdm_authentication_confirmation_request, encryption_context,
                                                 server_context.async_spacebridge_client)
    resp = yield r.content()

    logger.info("Completed MDM Authentication Request with response={}, code={}, request_id={}"
                .format(resp, r.code, request_id))

    defer.returnValue(mdm_authentication_confirmation_request)


class ServerRegistrationContext(object):
    """
    Interface for the server side aspect of MDM registration. Implementers are required to implement the following
    methods:
        - validate (username, password, device_info) -> boolean
            perform server side validation on whether the mdm registration request can proceed
        - create_session_token: (username, password) -> string
            generate a server side session token given a username and password
        - get_server_version: () -> string
            return the the current server side version number
        - persist_device_info: (DeviceInfo, username) -> None
            persist the device to the server side
    """
    __metaclass__ = ABCMeta

    def __init__(self, config):
        self.config = config
        self.async_spacebridge_client = AsyncSpacebridgeClient(config)

    @abstractmethod
    def validate(self, username, password, device_info):
        """
        Validates a mdm registration request. If the request is invalid, raises a
        CloudgatewayMdmRegistrationError
        Args:
            username:
            password:
            device_info:

        Returns:

        """
        raise NotImplementedError

    @abstractmethod
    def create_session_token(self, username, password):
        """
        Create a session token given a username and password
        Args:
            username:
            password:

        Returns: string representing session token

        """
        raise NotImplementedError

    @abstractmethod
    def get_server_version(self):
        """
        Returns (String): version of the server
        """
        raise NotImplementedError

    @abstractmethod
    def get_deployment_name(self):
        """
        Returns (String): name of the server
        """
        raise NotImplementedError

    @abstractmethod
    def persist_device_info(self, device_info, username):
        """
        Persist device info to the server

        Args:
            username: (String)
            device_info (DeviceInfo)
        Returns (None)

        """
        raise NotImplementedError

    @abstractmethod
    def get_mdm_signing_key(self):

        """

        Returns (Byte String): Mdm Signing key used to validate MDM registration requests

        """
        raise NotImplementedError

    @abstractmethod
    def get_server_type(self):
        """

        Returns (String): type of the server

        """
        raise NotImplementedError
