"""
(C) 2019 Splunk Inc. All rights reserved.

Message Processing module for taking serialized protobuf
messages received over websocket, process them and take the
appropriate action (fetch alerts, add subscription, etc) and
produce a serialized protobuf message to send back.
"""

import sys
import base64
from functools import partial

from spacebridgeapp.util import py23
from spacebridgeapp.messages.request_context import RequestContext
from spacebridgeapp.request.spacebridge_request_processor import unregister_device, mdm_authentication_request
from spacebridgeapp.messages.send_response import send_response
from spacebridgeapp.rest.devices.user_devices import public_keys_for_device
from spacebridgeapp.rest.clients.async_client_factory import AsyncClientFactory
from spacebridgeapp.util.shard import default_shard_id
from spacebridgeapp.versioning import app_version, minimum_build, is_version_ok
from spacebridgeapp.versioning.client_minimum import format_version
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, SERVER_SUBSCRIPTION_RESPONSE, \
    SERVER_SUBSCRIBE_RESPONSE, CLIENT_SINGLE_REQUEST, CLIENT_SUBSCRIPTION_MESSAGE, UNREGISTER_EVENT, \
    MDM_REGISTRATION_REQUEST, SERVER_SUBSCRIBE_UPDATE_RESPONSE, DRONE_MODE_TV_SUBSCRIBE, DRONE_MODE_IPAD_SUBSCRIBE
from cloudgateway.private.encryption.encryption_handler import encrypt_for_send, decrypt_for_receive, sign_detached, \
    sign_verify
from spacebridgeapp.util.guid_generator import get_guid
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeError, OperationHaltedError
from spacebridgeapp.request import connectivity_test_request_processor
from spacebridgeapp.request.request_processor import parse_session_token, parse_run_as_credentials
from spacebridgeapp.subscriptions import subscription_processor
from spacebridgeapp.request.request_list import REQUESTS, SUBSCRIPTION_REQUESTS, ENCRYPTION_CONTEXT
from spacebridgeapp.request.request_type import RequestType
from spacebridgeapp.metrics.websocket_metrics import send_websocket_metrics_to_telemetry
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.drone_mode.drone_mode_subscription_requests import process_subscriptions
from splapp_protocol import envelope_pb2
from splapp_protocol import common_pb2
from spacebridge_protocol import websocket_pb2
from spacebridge_protocol import sb_common_pb2
from twisted.internet import defer
from twisted.python import context

from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', SPACEBRIDGE_APP_NAME, 'lib']))

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_message_processor.log", "message_processor")


@defer.inlineCallbacks
def process(system_auth_header, message, websocket_protocol, async_client_factory,
            guid_generator=get_guid, shard_id=None):
    """Accepts a message which is assumed to be serialized using protobuf,
    deserializes the message, unencrypts the payload and routes to the appropriate
    processor depending on the type of message.

    For example, we check whether the message is a client single request, if it is,
    we call the process_request method to process the contents. Analagously, we have
    methods for other message types as well such as process_subscription.

    Arguments:
        message {serialized proto} -- serialized protobuf object

    Returns:
        Serialized Application Message representing response from the server
    """

    # Deserialize Signed Envelope
    signed_envelope = parse_signed_envelope(message)

    # Deserialize application message
    if signed_envelope.messageType == sb_common_pb2.SignedEnvelope.MESSAGE_TYPE_APPLICATION_MESSAGE:
        LOGGER.info("message=RECEIVED_ENVELOPE type=application_message")
        application_message = parse_application_message(signed_envelope.serialized)
    elif signed_envelope.messageType == sb_common_pb2.SignedEnvelope.MESSAGE_TYPE_SPACEBRIDGE_MESSAGE:
        # TODO: error handling
        LOGGER.info("message=RECEIVED_ENVELOPE type=spacebridge_message")
        spacebridge_message = parse_spacebridge_message(signed_envelope.serialized)
        handle_spacebridge_message(system_auth_header, spacebridge_message,
                                   async_client_factory.splunk_client(), async_client_factory.kvstore_client())
        defer.returnValue(True)
    else:
        LOGGER.info("message=RECEIVED_ENVELOPE type={}".format(signed_envelope.messageType))
        defer.returnValue("Unknown message type")

    message_sender = application_message.sender
    keys = yield public_keys_for_device(message_sender, system_auth_header, async_client_factory.kvstore_client())

    sender_sign_public_key, sender_encrypt_public_key = keys

    encryption_context = websocket_protocol.encryption_context
    sodium_client = encryption_context.sodium_client

    decryptor = partial(decrypt_for_receive,
                        sodium_client,
                        encryption_context.encrypt_public_key(),
                        encryption_context.encrypt_private_key())
    encryptor = partial(encrypt_for_send,
                        sodium_client,
                        sender_encrypt_public_key)

    signer = partial(sign_detached, sodium_client, encryption_context.sign_private_key())

    generichash = encryption_context.generichash_raw

    if not sign_verify(sodium_client, sender_sign_public_key, signed_envelope.serialized, signed_envelope.signature):
        defer.returnValue("Signature validation failed")

    server_response_id = guid_generator()
    client_application_message = parse_client_application_message(application_message, decryptor)

    if application_message.ByteSize() == 0 or client_application_message.ByteSize() == 0:
        defer.returnValue("Unknown message type")

    server_application_message = envelope_pb2.ServerApplicationMessage()

    # Check if message is a request or subscription and then populate the server_application_response
    request_context = yield process_message(message_sender,
                                            client_application_message,
                                            server_application_message,
                                            async_client_factory,
                                            websocket_protocol.encryption_context,
                                            server_response_id,
                                            system_auth_header,
                                            shard_id)

    response = yield send_response(request_context,
                                   message_sender,
                                   server_application_message,
                                   websocket_protocol,
                                   encryptor,
                                   signer,
                                   generichash)

    # Post processing function
    yield post_process_message(request_context,
                               server_application_message,
                               async_client_factory,
                               guid_generator)
    defer.returnValue(response)


@defer.inlineCallbacks
def post_process_message(request_context,
                         input_server_application_message,
                         async_client_factory,
                         guid_generator):
    # Post processing on serverSubscriptionResponse
    if input_server_application_message.HasField(SERVER_SUBSCRIPTION_RESPONSE):
        try:
            # Create Server Application Message to return for post_processing
            server_application_message = envelope_pb2.ServerApplicationMessage()

            # Populate a server_subscription_update which
            server_subscription_update = server_application_message.serverSubscriptionUpdate
            server_subscription_update.requestId = guid_generator()

            # Get subscription_id
            server_subscription_response = input_server_application_message.serverSubscriptionResponse
            subscription_id = server_subscription_response.subscriptionId
            server_subscription_update.subscriptionId = subscription_id

            if server_subscription_response.HasField(SERVER_SUBSCRIBE_RESPONSE):
                if (server_subscription_response.serverSubscribeResponse.HasField(DRONE_MODE_TV_SUBSCRIBE) or
                   server_subscription_response.serverSubscribeResponse.HasField(DRONE_MODE_IPAD_SUBSCRIBE)):
                    yield process_subscriptions(request_context,
                                                async_client_factory)

                else:
                    map_post_search = server_subscription_response.serverSubscribeResponse.postSearch or None
                    yield subscription_processor.process_subscription(request_context,
                                                                      subscription_id,
                                                                      server_subscription_update,
                                                                      async_client_factory,
                                                                      guid_generator,
                                                                      map_post_search=map_post_search)
        except SpacebridgeError as e:
            LOGGER.exception("SpacebridgeError during post_process_message")
            e.set_proto(server_subscription_update)

        except Exception as e:
            LOGGER.exception("Unhandled exception during post_process_message")
            server_subscription_update.error.code = common_pb2.Error.ERROR_UNKNOWN
            server_subscription_update.error.message = str(e)

        # Send out response if any errors or an update is encountered
        if not server_subscription_update.WhichOneof('subscription_update'):
            LOGGER.info("No Post Processing Response required for subscription_id={}".format(subscription_id))
            defer.returnValue(None)

        # Send out response if update is specified, returns errors and single saved search responses
        defer.returnValue(server_application_message.SerializeToString())


@defer.inlineCallbacks
def process_message(message_sender, client_application_message, server_application_message, async_client_factory,
                    encryption_context, server_response_id, system_auth_header, shard_id):
    device_id = py23.b64encode_to_str(message_sender)

    encryption_context = encryption_context

    if client_application_message.HasField(CLIENT_SINGLE_REQUEST):
        request_object = client_application_message.clientSingleRequest
        response_object = server_application_message.serverSingleResponse
        response_object.replyToMessageId = request_object.requestId
        response_object.serverVersion = str(app_version())

        processor = process_request
        request_type = CLIENT_SINGLE_REQUEST

    elif client_application_message.HasField(CLIENT_SUBSCRIPTION_MESSAGE):
        request_object = client_application_message.clientSubscriptionMessage

        # pings have a special case response, really they could be in their own modular input
        if client_application_message.clientSubscriptionMessage.HasField(RequestType.CLIENT_SUBSCRIPTION_PING.value):
            response_object = server_application_message.serverSubscriptionPing
        else:
            response_object = server_application_message.serverSubscriptionResponse
            response_object.replyToMessageId = request_object.requestId
            response_object.serverVersion = str(app_version())

        processor = process_subscription
        request_type = CLIENT_SUBSCRIPTION_MESSAGE

    else:
        LOGGER.warn("No suitable message type found client application request")
        defer.returnValue("device_id={}".format(device_id))

    response_object.requestId = server_response_id

    if request_object.HasField("runAs"):
        LOGGER.debug("run as credentials is present")
        auth_header = yield parse_run_as_credentials(encryption_context, system_auth_header,
                                                     async_client_factory, request_object.runAs)
    else:
        auth_header = parse_session_token(encryption_context, request_object.sessionToken)

    request_context = RequestContext(auth_header, device_id=device_id,
                                     raw_device_id=message_sender, request_id=request_object.requestId,
                                     current_user=auth_header.username, system_auth_header=system_auth_header,
                                     client_version=request_object.clientVersion, user_agent=request_object.userAgent,
                                     shard_id=shard_id)

    try:
        validate_client_version(request_object, response_object)
        yield auth_header.validate(async_client_factory.splunk_client(), LOGGER, request_context)
        should_send_response = yield context.call({'request_context': request_context}, processor, request_context,
                                                  encryption_context, request_object, response_object,
                                                  async_client_factory)

        # If we aren't sending a response in this request clear the server_application_message
        if not should_send_response:
            server_application_message.Clear()

    except OperationHaltedError:
        server_application_message.ClearField('app_message')
    except SpacebridgeError as e:
        LOGGER.exception("SpacebridgeError during process_message")
        e.set_proto(response_object)

    except Exception as e:
        LOGGER.exception("Unhandled exception during process_message")
        response_object.error.code = common_pb2.Error.ERROR_UNKNOWN
        response_object.error.message = str(e)

    LOGGER.info('Finished processing message. {}'.format(request_context))
    defer.returnValue(request_context)


def validate_client_version(request_object, response_object):
    user_agent = request_object.userAgent or "invalid"
    user_agent_parts = user_agent.split('|')
    app_id = user_agent_parts[0]
    LOGGER.debug("Checking {} version {}".format(app_id, request_object.clientVersion))
    if not is_version_ok(app_id, request_object.clientVersion):
        app_min_build = minimum_build(app_id)

        raise SpacebridgeError('Client does not meet minimum version: {}'.format(app_min_build),
                               code=common_pb2.Error.ERROR_REQUEST_UPGRADE_REQUIRED,
                               client_minimum_version=format_version(request_object.clientVersion, app_min_build))


def parse_spacebridge_message(serialized_spacebridge_message):
    """
    Deserialize spacebridge message and if it is an error message, log it.
    :param serialized_spacebridge_message: serialized SpacebridgeMessage proto
    :return: None
    """
    spacebridge_message = websocket_pb2.SpacebridgeMessage()
    try:
        spacebridge_message.ParseFromString(serialized_spacebridge_message)

        if spacebridge_message.HasField("error"):
            LOGGER.info("Received Spacebridge Error with message={}".format(spacebridge_message.error.message))

    except Exception:
        LOGGER.exception("Exception parsing spacebridge message")

    return spacebridge_message


def handle_spacebridge_message(auth_header, spacebridge_message, async_client_factory,
                               encryption_context):
    """

    :type async_client_factory: AsyncClientFactory
    """
    if spacebridge_message.HasField(UNREGISTER_EVENT):
        LOGGER.info("Spacebridge unregister event")
        unregister_device(auth_header, spacebridge_message.unregisterEvent, async_client_factory.splunk_client(),
                          async_client_factory.kvstore_client())
    if spacebridge_message.HasField(MDM_REGISTRATION_REQUEST):
        request_id = get_guid()
        LOGGER.info("message=RECEIVED_ENVELOPE type={}, creating request_id={}".format(MDM_REGISTRATION_REQUEST,
                                                                                       request_id))
        mdm_authentication_request(auth_header, spacebridge_message.mdmRegistrationRequest, async_client_factory,
                                   encryption_context, request_id)
    else:
        LOGGER.info("Unknown spacebridge message received")


def parse_signed_envelope(serialized_signed_envelope):
    """Deserialize a serialized Signed Envelope Proto object

    Arguments:
        serialized_signed_envelope {[type]} -- [description]

    Returns:
        [type] -- [description]
    """

    signed_envelope = sb_common_pb2.SignedEnvelope()
    try:
        signed_envelope.ParseFromString(serialized_signed_envelope)
    except:
        LOGGER.exception("Exception deserializing Signed Envelope")

    return signed_envelope


def parse_application_message(serialized_message):
    """Deserialize a serialized Application Message object

    Arguments:
        serialized_message {bytes}

    Returns:
        ApplicationMessage Proto
    """

    application_message = websocket_pb2.ApplicationMessage()

    try:
        application_message.ParseFromString(serialized_message)
    except:
        LOGGER.exception("Exception deserializing protobuf")

    return application_message


def parse_client_application_message(application_message, decrypt):
    """Take an Application Message proto, extract the payload,
    decrypt it and then deserialize it as a Client Application
    Request Proto.

    Arguments:
        application_message {Application Message Proto}

    Returns:
        ClientApplicationMessage Proto
    """

    client_application_message = envelope_pb2.ClientApplicationMessage()
    try:
        encrypted_payload = application_message.payload
        decrypted_payload = decrypt(encrypted_payload)
        client_application_message.ParseFromString(decrypted_payload)
    except Exception as e:
        LOGGER.exception("Exception deserializing payload from envelope")

    return client_application_message


@defer.inlineCallbacks
def process_request(request_context,
                    encryption_context,
                    client_single_request,
                    server_single_response,
                    async_client_factory):
    """ Accepts the input client single request proto and a server
        application response proto.

        Based on the type of the request, routes to the appropriate
        method for the request type, e.g.
            1. alerts list request
            2. delete alert request
            3. dashboard list request
            4. dashboard get request
            5. etc.
        and populates the Server Application Response proto accordingly.

        Arguments:
            client_application_message {ClientApplicationMessage Proto}
            server_application_response {ServerApplicationResponse Proto}

         Return:
            N
    """
    should_send = yield process_request_list(request_context,
                                             client_single_request,
                                             server_single_response,
                                             async_client_factory,
                                             REQUESTS,
                                             encryption_context)

    # if should_send has value return it
    if should_send is not None:
        defer.returnValue(send_response)

    # Special Case Processing
    if client_single_request.HasField(RequestType.CONNECTIVITY_TEST_REQUEST.value):
        LOGGER.info("type={}".format(RequestType.CONNECTIVITY_TEST_REQUEST.name))
        send_websocket_metrics_to_telemetry(
            RequestType.CONNECTIVITY_TEST_REQUEST.name, request_context, async_client_factory.telemetry_client(),
            LOGGER, useragent=client_single_request.userAgent, params=get_params_for_metrics(client_single_request))

        yield connectivity_test_request_processor.process_connectivity_test_request(
            request_context,
            encryption_context,
            client_single_request,
            server_single_response,
            async_client_factory.spacebridge_client(),
            async_client_factory.kvstore_client())

        # The connectivity_test_request is sent over https so we don't want to send response over wss as well
        defer.returnValue(False)
    else:
        # Fall through here then message type was not found
        LOGGER.info('type=MESSAGE_NOT_SUPPORTED')
        message_not_supported()
        defer.returnValue(True)


@defer.inlineCallbacks
def process_subscription(request_context,
                         encryption_context,
                         client_subscription_message,
                         server_subscription_response,
                         async_client_factory):
    """
    Analogous method as process_request for processing ClientSingleRequests.

    Base on the type of subscription request routes to the appropriate handler
    1. Client Subscribe Request
    2. Client Unsubscribe Request
    3. Client Subscription Ping

    :param request_context:
    :param encryption_context:
    :param client_subscription_message:
    :param server_subscription_response:
    :param async_client_factory:
    :return: None - modified the server_application_response
    """
    should_send = yield process_request_list(request_context,
                                             client_subscription_message,
                                             server_subscription_response,
                                             async_client_factory,
                                             SUBSCRIPTION_REQUESTS,
                                             encryption_context)
    # if should_send has value return it
    if should_send is not None:
        defer.returnValue(send_response)

    # Fall through if no valid message found
    LOGGER.info('type=MESSAGE_NOT_SUPPORTED')
    message_not_supported()

    # By default return a response object over wss
    defer.returnValue(True)


@defer.inlineCallbacks
def process_request_list(request_context,
                         client_message,
                         server_response,
                         async_client_factory,
                         request_list,
                         encryption_context):
    """
    Helper method used to process request from a request_list
    :param request_context:
    :param client_message:
    :param server_response:
    :param async_client_factory:
    :param request_list:
    :return:
    """
    async_telemetry_client = async_client_factory.telemetry_client()
    useragent = client_message.userAgent

    for request in request_list:
        enum, process_function, args = request
        if client_message.HasField(enum.value):
            LOGGER.info("type={}".format(enum.name))
            if enum.name != "CLIENT_SUBSCRIPTION_PING":
                send_websocket_metrics_to_telemetry(
                    enum.name, request_context, async_telemetry_client, LOGGER, useragent=useragent,
                    params=get_params_for_metrics(client_message))

            # Build argument map
            kwargs = {arg: async_client_factory.from_value(arg) for arg in args}

            if ENCRYPTION_CONTEXT in args:
                kwargs[ENCRYPTION_CONTEXT] = encryption_context

            yield process_function(
                request_context,
                client_message,
                server_response,
                **kwargs)
            defer.returnValue(True)


def message_not_supported():
    raise SpacebridgeError('message type not supported', code=common_pb2.Error.ERROR_REQUEST_NOT_SUPPORTED)


def get_params_for_metrics(client_message):
    return {
        'requestId': client_message.requestId,
        'messageSize': client_message.ByteSize(),
        'splappVersion': str(app_version())
    }
