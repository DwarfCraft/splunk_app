"""
(C) 2019 Splunk Inc. All rights reserved.
"""
import requests

from cloudgateway.private.registration.util import sb_auth_endpoint, sb_auth_header
from spacebridge_protocol import http_pb2
from cloudgateway.private.exceptions import rest as RestException


def submit_auth_code(auth_code, encryption_context, config):
    """
    Given an auth code, submit it to cloudgateway's auth endpoint. Raise an exception if cannot reach cloudgateway
    :param auth_code
    :param encryption_context
    :return: seriealized protobuf response from cloudgateway
    """
    try:
        spacebridge_header = {'Authorization': sb_auth_header(encryption_context)}
        return requests.get(sb_auth_endpoint(auth_code, config),
                            headers=spacebridge_header,
                            proxies=config.get_proxies()
                            )
    except Exception as e:
        raise RestException.CloudgatewayServerError('Unable to reach cloudgateway: {0}'.format(e), 503)


def parse_spacebridge_response(response):
    """
    Takes the serialized protobuf response from cloudgateway's auth endpoint, parses it and returns the deserialized
    protobuf object
    :param response:
    :return: AuthenticationQueryResponse protobuf object
    """

    spacebridge_response = http_pb2.AuthenticationQueryResponse()
    spacebridge_response.ParseFromString(response.content)

    if spacebridge_response.HasField('error'):
        if response.status_code == 500:
            raise RestException.CloudgatewayServerError('cloudgateway encountered an internal error: %s'
                                                        % spacebridge_response.error.message, 500)

        raise RestException.CloudgatewayServerError(
            'cloudgateway request error: %s' % spacebridge_response.error.message,
            response.status_code
        )

    if not str(response.status_code).startswith('2'):
        raise RestException.CloudgatewayServerError("cloudgateway error: %s" % str(response.content), response.status_code)

    return spacebridge_response