"""
(C) 2019 Splunk Inc. All rights reserved.

Module to build subscription update message
"""

from spacebridge_protocol import http_pb2
from spacebridge_protocol import sb_common_pb2
from spacebridge_protocol import websocket_pb2
from splapp_protocol import common_pb2
from splapp_protocol import envelope_pb2
from spacebridgeapp.data.subscription_data import DroneModeTVEvent, DroneModeiPadEvent


def build_drone_mode_subscription_update(request_id,
                                         subscription_id,
                                         update_id,
                                         subscription_update):
    """
    Build Subscription Update proto
    :param request_id:
    :param subscription_id:
    :param update_id:
    :param subscription_update:
    :return:
    """
    server_application_message = envelope_pb2.ServerApplicationMessage()

    server_application_message.serverSubscriptionUpdate.requestId = request_id
    server_application_message.serverSubscriptionUpdate.subscriptionId = subscription_id
    server_application_message.serverSubscriptionUpdate.updateId = update_id

    # if/else case statement for drone mode subscription_update types
    # TV events
    if isinstance(subscription_update, DroneModeTVEvent):
        subscription_update.set_protobuf(
            server_application_message.serverSubscriptionUpdate.droneModeTVEvent)

    # iPad Events
    elif isinstance(subscription_update, DroneModeiPadEvent):
        subscription_update.set_protobuf(
            server_application_message.serverSubscriptionUpdate.droneModeiPadEvent)

    else:
        server_application_message.serverSubscriptionUpdate.error.code = common_pb2.Error.ERROR_UNKNOWN
        server_application_message.serverSubscriptionUpdate.error.message = 'Unexpected Error!'

    return server_application_message


def build_signed_envelope(signed_envelope, recipient, sender_id, request_id, encrypted_payload, sign):
    """
    Build signed envelope application message
    :param signed_envelope:
    :param recipient:
    :param sender_id:
    :param request_id:
    :param encrypted_payload:
    :param sign:
    :return:
    """
    application_message = websocket_pb2.ApplicationMessage()
    application_message.version = websocket_pb2.ApplicationMessage.MAJOR_VERSION_V1
    application_message.id = request_id
    application_message.to = recipient
    application_message.sender = sender_id
    application_message.payload = encrypted_payload

    serialized = application_message.SerializeToString()
    signature = sign(serialized)

    signed_envelope.messageType = sb_common_pb2.SignedEnvelope.MESSAGE_TYPE_APPLICATION_MESSAGE
    signed_envelope.signature = signature
    signed_envelope.serialized = serialized
