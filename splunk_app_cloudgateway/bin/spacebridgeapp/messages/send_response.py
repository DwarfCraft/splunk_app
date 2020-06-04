"""
(C) 2019 Splunk Inc. All rights reserved.

Separate module to capture send methods
"""

from twisted.internet import defer
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from spacebridge_protocol import websocket_pb2, sb_common_pb2

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_send_processor.log", "send_processor")


@defer.inlineCallbacks
def send_response(request_context, message_sender, server_application_response, websocket_protocol, encrypt, sign, generichash):
    if not server_application_response.WhichOneof('app_message'):
        LOGGER.info("No response necessary")
        defer.returnValue(None)

    # Take server payload and wrap in an envelope
    payload = server_application_response.SerializeToString()
    encrypted_payload = encrypt(payload)

    signed_envelope = yield build_envelope(encrypted_payload,
                                           message_sender,
                                           websocket_protocol,
                                           request_context.request_id,
                                           sign,
                                           generichash)

    serialized_envelope = signed_envelope.SerializeToString()

    LOGGER.info("Signed Envelope size_bytes=%d", signed_envelope.ByteSize())

    try:
        yield websocket_protocol.sendMessage(serialized_envelope, isBinary=True)
        LOGGER.info("message=SENT_BACK")
    except Exception:
        LOGGER.exception("Error sending message back")

    defer.returnValue(serialized_envelope)


def build_envelope(message, recipient, websocket_protocol, request_id, sign, generichash):
    """Takes the Server Application Response, encrypts it and constructs
    top level Signed Envelope which is sent back to Spacebridge.

    Arguments:
        :param message: Encrypted and processed message
        :param recipient: Who the message will be sent to
        :param websocket_protocol: The protocol used to send the method
        :param request_id: The id we associate with the request on the server side
        :param sign: A function that takes in a message and returns a digital signature
    Returns:
        SignedEnvelope Proto
    """

    sodium_client = websocket_protocol.encryption_context.sodium_client

    # First construct application level message
    application_message = websocket_pb2.ApplicationMessage()
    application_message.version = websocket_pb2.ApplicationMessage.MAJOR_VERSION_V1
    application_message.id = request_id
    application_message.to = recipient
    application_message.sender = websocket_protocol.encryption_context.sign_public_key(transform=generichash)
    application_message.payload = message

    serialized = application_message.SerializeToString()

    # Construct Signed Envelope
    signed_response = sb_common_pb2.SignedEnvelope()
    signed_response.serialized = serialized
    signed_response.messageType = sb_common_pb2.SignedEnvelope.MESSAGE_TYPE_APPLICATION_MESSAGE
    signed_response.signature = sign(serialized)

    LOGGER.info("Finished Signing envelope")
    return signed_response
