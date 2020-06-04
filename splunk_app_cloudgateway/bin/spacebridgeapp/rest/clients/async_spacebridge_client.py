"""
(C) 2019 Splunk Inc. All rights reserved.

Module providing client for making asynchronous requests to Spacebridge API
"""

from spacebridgeapp.rest.clients.async_client import noverify_treq_instance
from spacebridgeapp.rest.clients.async_client import AsyncClient
from spacebridgeapp.util.config import cloudgateway_config as config


class AsyncSpacebridgeClient(AsyncClient):

    def __init__(self):
        self.https_proxy = config.get_https_proxy_settings()
        AsyncClient.__init__(self, treq=noverify_treq_instance(https_proxy=self.https_proxy))

    def async_send_request(self, api, auth_header, data='', headers={}):
        """
        Generic Async send request
        :param api:
        :param auth_header:
        :param data:
        :param headers:
        :return:
        """
        if self.https_proxy and self.https_proxy['auth']:
            headers['Proxy-Authorization'] = 'Basic ' + self.https_proxy['auth']

        rest_uri = "https://%s" % config.get_spacebridge_server() + api
        return self.async_post_request(uri=rest_uri,
                                       auth_header=auth_header,
                                       data=data,
                                       headers=headers)

    def async_send_notification_request(self, auth_header, data='', headers={}):
        """
        API to send notifications
        :param auth_header:
        :param data:
        :param headers:
        :return:
        """
        return self.async_send_request('/api/notifications', auth_header, data, headers)

    def async_send_message_request(self, auth_header, data='', headers={}):
        """
        API to send messages
        :param auth_header:
        :param data:
        :param headers:
        :return:
        """
        return self.async_send_request('/api/deployments/messages', auth_header, data, headers)


    def async_send_storage_request(self, payload, content_type, signature, auth_header,
                                   request_id):
        """
        API to store resources on spacebridge
        :param payload: Bytes
        :param content_type: MIME type
        :param signature:
        :param auth_header:
        :param request_id:
        :param logger:
        :return: Treq.Response object
        """

        headers = {}

        headers['x-amz-meta-signature'] = signature.encode("hex")
        headers['content-type'] = "application/octet-stream"
        headers['x-amz-meta-content-type'] = content_type
        headers['X-B3-TraceId'] = request_id

        return self.async_send_request('/storage/assets', auth_header, data=payload, headers=headers)

