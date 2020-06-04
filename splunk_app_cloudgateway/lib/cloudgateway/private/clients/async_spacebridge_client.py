"""
(C) 2019 Splunk Inc. All rights reserved.

Module providing client for making asynchronous requests to Spacebridge API
"""

from cloudgateway.private.clients.async_client import noverify_treq_instance
from cloudgateway.private.clients.async_client import AsyncClient

class AsyncSpacebridgeClient(AsyncClient):
    """
    Client for making asynchronous HTTP requests to spacebridge
    """

    def __init__(self, config):
        self.https_proxy = config.get_https_proxy_settings()
        self.config = config
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

        rest_uri = "https://%s" % self.config.get_spacebridge_server() + api
        return self.async_post_request(uri=rest_uri,
                                       auth_header=auth_header,
                                       data=data,
                                       headers=headers
                                      )
