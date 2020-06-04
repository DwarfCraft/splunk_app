"""
(C) 2019 Splunk Inc. All rights reserved.

Module to process Alerts Requests
"""

import json

import jsonpickle
from spacebridgeapp.util.constants import OR_OPERATOR, LESS_THAN_OPERATOR, GREATER_THAN_OPERATOR, SORT, LIMIT, QUERY, \
    KEY
from spacebridgeapp.util import constants
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from splapp_protocol import request_pb2
from spacebridgeapp.logging import setup_logging
from twisted.internet import defer
from twisted.web import http

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_alerts_request_processor.log", "alerts_request_processor")


@defer.inlineCallbacks
def process_alerts_list_request(request_context,
                                client_single_request,
                                server_single_response,
                                async_kvstore_client):
    """
    This method will process alerts list requests

    :param request_context:
    :param client_single_request:
    :param server_single_response:
    :param async_kvstore_client:
    :return:
    """

    yield populate_alerts_list_response(request_context,
                                        client_single_request,
                                        server_single_response,
                                        async_kvstore_client)


@defer.inlineCallbacks
def process_alert_get_request(request_context,
                              client_single_request,
                              server_single_response,
                              async_kvstore_client):
    """
    This method will process an alert get request to fetch a single alert
    :param request_context:
    :param client_single_request: clientSingleRequest proto with alertGetRequest field
    :param server_single_response: ServerSingleResponse opbject with alertGetResponse field
    :param async_kvstore_client:
    :return: void (modifies the server single response proto)
    """

    LOGGER.info("Fetching alert get for alert=%s", client_single_request.alertGetRequest.alertId)

    alert_id = client_single_request.alertGetRequest.alertId

    alert = yield fetch_alert(request_context=request_context,
                              alert_id=alert_id,
                              async_kvstore_client=async_kvstore_client)
    alert.set_protobuf(server_single_response.alertGetResponse.alert)
    LOGGER.info("Finished processing alert get request")


@defer.inlineCallbacks
def process_alerts_delete_request(request_context, client_single_request, server_single_response, async_kvstore_client):
    """
    This method will process alerts delete requests
    :param request_context:
    :param client_single_request: reference client request object
    :param server_single_response:  pass-by-reference return object
    :param async_kvstore_client:
    """
    LOGGER.info("Processing Alerts Delete Request")

    device_id = request_context.device_id
    alert_ids = client_single_request.alertsDeleteRequest.alertIds

    yield delete_alerts_for_device(request_context, device_id, alert_ids, async_kvstore_client)

    server_single_response.alertsDeleteResponse.alertIds.extend(alert_ids)
    LOGGER.info("Finished processing Alerts Delete Request")


@defer.inlineCallbacks
def populate_alerts_list_response(request_context,
                                  client_single_request,
                                  single_server_response,
                                  async_kvstore_client):
    """
    Takes a client_single_request object and a device id and fetches the corresponding alert ids from kv store
    the single_server_response input proto with the fetched alerts.
    :param request_context:
    :param client_single_request: proto of client_single_request provided by the client
    :param single_server_response: server_single_response proto to be returned by splapp
    :param async_kvstore_client: client to make requests to kv store
    :return: No return. Single Server Response input is mutated with return values
    """

    continuation_id = client_single_request.alertsListRequest.continuationId
    max_results = client_single_request.alertsListRequest.maxResults
    order = client_single_request.alertsListRequest.order

    LOGGER.info("Start populate_alerts_list_response")

    # fetch alert ids for device and then fetch corresponding alert bodies
    alert_ids = yield fetch_alert_ids(request_context=request_context,
                                      order=order,
                                      continuation_id=continuation_id,
                                      num_results=max_results,
                                      async_kvstore_client=async_kvstore_client)
    alert_bodies = yield fetch_alert_bodies(request_context=request_context,
                                            alert_ids=alert_ids,
                                            async_kvstore_client=async_kvstore_client,
                                            order=order)
    alert_protos = []
    for alert in alert_bodies:
        alert.detail = None
        alert_protos.append(alert.to_protobuf())

    # populate server response proto
    single_server_response.alertsListResponse.continuationId = continuation_id

    # for some reason, direct assignment for repeated fields throws an error, so we do it manually. First delete
    # any elements in the list and then add the fields we want.
    del single_server_response.alertsListResponse.alerts[:]
    single_server_response.alertsListResponse.alerts.extend(alert_protos)
    single_server_response.alertsListResponse.order = order

    if len(alert_protos) > 0:
        single_server_response.alertsListResponse.nextContinuationId = alert_protos[-1].notification.createdAt

    LOGGER.info("Finished populating response for alerts list request with num_alerts=%d", len(alert_protos))



@defer.inlineCallbacks
def fetch_alert_bodies(request_context,
                       alert_ids=[],
                       async_kvstore_client=None,
                       order=None):
    """
    Takes a list of alert ids and returns a list of the corresponding alert data objects by fetching them from
    kv store
    :param request_context:
    :param alert_ids: list of alert ids
    :order: proto specifying whether to return results in ascending or descending order by timestamp
    :param async_kvstore_client: instance of AsyncKvStoreClient
    :param order:
    :return: ordered list of alert objects corresponding to the input alert ids
    """

    if alert_ids is None or not alert_ids:
        defer.returnValue([])

    query = {OR_OPERATOR: [{KEY:alert_id} for alert_id in alert_ids]}
    sort_order = (1 if order == request_pb2.ASCENDING else -1)
    sort_param = "notification.created_at:%d" % sort_order

    alert_bodies_response = yield async_kvstore_client.async_kvstore_get_request(
        constants.MOBILE_ALERTS_COLLECTION_NAME,
        params={QUERY: json.dumps(query), SORT: sort_param},
        auth_header=request_context.auth_header)

    if alert_bodies_response.code != http.OK:
        message = yield alert_bodies_response.text()
        raise SpacebridgeApiRequestError("Call to fetch alert bodies failed with message={}".format(message))

    alert_bodies_response_json = yield alert_bodies_response.json()
    alerts_list = []

    # If we received the alert bodies, go through each one and attemp to convert it back to an alert object
    for alert_json in alert_bodies_response_json:
        try:
            alert = jsonpickle.decode(json.dumps(alert_json))
            alert.notification.alert_id = alert_json[KEY]
            alerts_list.append(alert)
        except json.JsonDecodeError:
            LOGGER.exception("Error decoding alert json=%s", alert_json)
        except Exception:
            LOGGER.exception("Exception in processing alert json=%s", alert_json)

    defer.returnValue(alerts_list)


@defer.inlineCallbacks
def delete_alerts_for_device(request_context, device_id, alert_ids, async_kvstore_client):
    """
    Delete a list of alert ids for a given device from the alert_recipient_devices collection. This is so that the
    alert is not fetched for that particular device in the feature. The actual body of the alert still exists in KV Store
    :param request_context:
    :param device_id: [string] id of device for which to remove the alert ids
    :param alert_ids: [list[string]] list of alert ids to be deleted
    :param async_kvstore_client:
    :return:
    """
    query = {OR_OPERATOR: [{"alert_id":alert_id, "device_id":device_id} for alert_id in alert_ids]}
    response = yield async_kvstore_client.async_kvstore_delete_request(collection=constants.ALERTS_RECIPIENT_DEVICES_COLLECTION_NAME,
                                                                       auth_header=request_context.auth_header,
                                                                       params={QUERY: json.dumps(query)})
    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError("Call to delete alert for user failed with message={}".format(message))



@defer.inlineCallbacks
def delete_all_alerts_for_device(request_context, device_id, async_kvstore_client):
    """
    Delete all alert ids for a given device from the alert_recipient_devices collection. This is so that the
    alert is not fetched for that particular device in the feature. The actual body of the alert still exists in KV Store
    :param request_context:
    :param device_id: [string] id of device for which to remove the alert ids
    :param alert_ids: [list[string]] list of alert ids to be deleted
    :param async_kvstore_client:
    :return:
    """
    query = {"device_id": device_id}
    response = yield async_kvstore_client.async_kvstore_delete_request(collection=constants.ALERTS_RECIPIENT_DEVICES_COLLECTION_NAME,
                                                                       auth_header=request_context.auth_header,
                                                                       params={QUERY: json.dumps(query)})
    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError("Call to delete all alert for user failed with message={}".format(message))


@defer.inlineCallbacks
def fetch_alert(request_context,
                alert_id=None,
                async_kvstore_client=None):
    """
    Retrieve a specific alert given the alert id, from KV Store

    :param request_context:
    :param alert_id:
    :param async_kvstore_client:
    :return:
    """

    query = {KEY: alert_id}
    response = yield async_kvstore_client.async_kvstore_get_request(
        constants.MOBILE_ALERTS_COLLECTION_NAME,
        params={QUERY: json.dumps(query)},
        auth_header=request_context.auth_header
    )

    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError("Call to fetch alert by alert_id={} failed with message={}"
                                         .format(alert_id, message))

    alert_json = yield response.json()
    alert = jsonpickle.decode(json.dumps(alert_json[0]))
    alert.notification.alert_id = alert_id
    defer.returnValue(alert)


@defer.inlineCallbacks
def fetch_alert_ids(request_context,
                    order=None,
                    continuation_id=None,
                    num_results=0,              # 0 works as unlimited with kvstore API
                    async_kvstore_client=None):

    """
    Fetches the ids of alerts for a particular device_id based on the order (ascending, descending) and the continuation
    id (which allows for pagination)

    :param request_context:
    :param order: order of alerts
    :param continuation_id: timestamp of last alert to paginatine on. "" if no pagination to be done.
    :param num_results: max number of results
    :param async_kvstore_client: handler for making http requests to kv store
    :return: deferred list of alert ids for the given device id
    """
    sort_order = (1 if order == request_pb2.ASCENDING else -1)
    alert_ids_table = constants.ALERTS_RECIPIENT_DEVICES_COLLECTION_NAME
    device_id = request_context.device_id

    if continuation_id is None or not continuation_id:
        # If the client provides no continuation id, then we fetch all alerts
        # belonging to the particular device id, sorted by the order provided by the client and then we take the top
        # K results.
        query = {QUERY: json.dumps({"device_id": device_id}),
                 SORT: "timestamp:%d" % sort_order,
                 LIMIT: num_results}
    else:
        # If the user provides a continuation id, which is a timestamp, we build a query to get the next K alerts
        # that happened after or before the timestamp (depending on which ordering is specified by the client)
        query = paginated_alert_query(sort_order, continuation_id, num_results, device_id)

    response = yield async_kvstore_client.async_kvstore_get_request(collection=alert_ids_table,
                                                                    params=query,
                                                                    auth_header=request_context.auth_header)

    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError(
            "Error fetching ids for paginated alerts for status_code={}, query={}, error={}"
            .format(response.code, json.dumps(query), message))

    response_json = yield response.json()
    defer.returnValue([alert["alert_id"] for alert in response_json])


def paginated_alert_query(order, alert_timestamp, num_results, device_id):
    """
    Given an ordering and timestamp, returns a KV store query for getting the next or previous K results
    (depending on order) occurring after (or before)  the given  timestamp
    """
    if order == -1:
        query = {"timestamp": {LESS_THAN_OPERATOR: alert_timestamp}, "device_id": device_id}
    else:
        query = {"timestamp": {GREATER_THAN_OPERATOR: alert_timestamp}, "device_id": device_id}

    return {QUERY: json.dumps(query),
            SORT: "timestamp:%d" % order,
            LIMIT: num_results}


@defer.inlineCallbacks
def process_alerts_clear_request(request_context, _client_single_request, server_single_response, async_kvstore_client):
    """
    Will find all alerts for the provided device, and remove the alert mappings for that device.  Does not affect
    the underlying alert bodies.
    :param request_context: A request context containing the device_id
    :param _client_single_request: ignored for now, a AlertsClearRequest protobuf message
    :param server_single_response: A ServerSingleResponse protobuf message
    :param async_kvstore_client:
    :return:
    """
    yield delete_all_alerts_for_device(request_context, request_context.device_id, async_kvstore_client)

    server_single_response.alertsClearResponse.SetInParent()
