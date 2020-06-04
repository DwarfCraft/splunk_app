"""
(C) 2019 Splunk Inc. All rights reserved.

Methods for sending latency metrics to telemetry
"""


def send_dashboard_list_request_metrics_to_telemetry(message_type,
                                                     latency,
                                                     request_context,
                                                     async_telemetry_client,
                                                     logger,
                                                     useragent=None):
    """
    Take a message type string and useragent string and log that information to telemetry
    :param message_type: String (e.g. DASHBOARD_LIST_REQUEST)
    :param latency: time taken to execute request
    :param request_context:
    :param async_telemetry_client:
    :param logger:
    :param useragent: String representing the user's device meta information
    :return:
    """
    payload = {
        "message_type": message_type,
        "latency": latency,
        "device_id": request_context.device_id,
        "useragent": useragent
    }

    return async_telemetry_client.post_metrics(payload, request_context.system_auth_header, logger)
