"""
(C) 2019 Splunk Inc. All rights reserved.
"""

from spacebridgeapp.rest.clients.async_client import AsyncClient
import splunk.rest as rest


class AsyncJubileeClient(AsyncClient):
    def get_api_key_uri(self):
        """
        Helper method to get uri for snl's api key api
        :return: [string]
        """
        rest_uri = rest.makeSplunkdUri()
        return '%sservicesNS/nobody/snl/snl/api_key/backend_api_key?output_mode=json' % rest_uri

    def get_hostname_uri(self):
        """
        Helper method to get uri for snl's hostname api
        :return: [string]
        """
        rest_uri = rest.makeSplunkdUri()
        return '%sservicesNS/nobody/snl/snl/settings/backend_settings?output_mode=json' % rest_uri

    def async_get_api_key(self, splunk_cookie, auth_header):
        """
        Makes async call and fetches snl's api key
        :param splunk_cookie: [String] splunk session token gotten from the /auth/login api
        :param auth_header: auth header object
        :return: deferred[String] apiKey
        """
        uri = self.get_api_key_uri()
        return self.async_get_request(uri, headers={'splunkd_8089':splunk_cookie}, auth_header=auth_header)

    def async_get_host_name(self, splunk_cookie, auth_header):
        """
        Makes async call and fetches hostname for snl api
        :param splunk_cookie: [String] splunk session token gotten from the /auth/login api
        :param auth_header: auth header object
        :return: deferred[String] apiKey
        :return: deferred[String] hostname
        """
        uri = self.get_hostname_uri()
        return self.async_get_request(uri, headers={'splunkd_8089':splunk_cookie}, auth_header=auth_header)
