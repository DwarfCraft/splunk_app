"""
(C) 2019 Splunk Inc. All rights reserved.

Module to build subscription update message
"""

from spacebridge_protocol import http_pb2
from spacebridge_protocol import sb_common_pb2
from spacebridge_protocol import websocket_pb2
from splapp_protocol import common_pb2
from splapp_protocol import envelope_pb2
from spacebridgeapp.data.subscription_data import ServerDashboardVisualizationEvent, ServerDashboardInputSearchEvent, \
    ServerSavedSearchEvent, ServerUdfDatasourceEvent
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeError


def build_send_subscription_update_request(recipient, sender_id, request_id,
                                           server_application_message,
                                           encrypt, sign):
    """
    Build send subscription update request to send to spacebridge send_message api
    :param recipient:
    :param sender_id:
    :param request_id:
    :param server_application_message
    :param encrypt:
    :param sign:
    :return:
    """
    send_message_request = http_pb2.SendMessageRequest()
    encrypted_payload = encrypt(server_application_message.SerializeToString())
    build_signed_envelope(send_message_request.signedEnvelope, recipient, sender_id, request_id, encrypted_payload, sign)
    return send_message_request


def build_splapp_subscription_update(request_id, subscription_id, update_id, subscription_update):
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

    # if/else case statement for subscription_update types
    if isinstance(subscription_update, ServerDashboardVisualizationEvent):
        subscription_update.set_protobuf(server_application_message.serverSubscriptionUpdate.dashboardVisualizationEvent)
    elif isinstance(subscription_update, ServerUdfDatasourceEvent):
        subscription_update.set_protobuf(server_application_message.serverSubscriptionUpdate.udfDataSourceEvent)
    elif isinstance(subscription_update, ServerDashboardInputSearchEvent):
        subscription_update.set_protobuf(server_application_message.serverSubscriptionUpdate.dashboardInputSearchEvent)
    elif isinstance(subscription_update, ServerSavedSearchEvent):
        subscription_update.set_protobuf(server_application_message.serverSubscriptionUpdate.serverSavedSearchResultEvent)
    elif isinstance(subscription_update, SpacebridgeError):
        subscription_update.set_proto(server_application_message.serverSubscriptionUpdate)
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
