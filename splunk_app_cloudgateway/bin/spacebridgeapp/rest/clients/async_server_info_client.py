"""
(C) 2019 Splunk Inc. All rights reserved.

Module providing client for making asynchronous requests about Splunk server info
"""
from spacebridgeapp.rest.clients.async_client import AsyncClient
from spacebridgeapp.util import constants
import splunk.rest as rest
from twisted.internet import defer
from twisted.web import http

from spacebridgeapp.logging import setup_logging
LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_async_server_info_client.log", "async_splunk_client")


class AsyncServerInfoClient(AsyncClient):

    def async_get_server_info(self, auth_header):
        """
        Async api call to get /server/info
        :param auth_header:
        :return:
        """
        uri = '%s/services/server/info' % rest.makeSplunkdUri()
        return self.async_get_request(uri=uri, auth_header=auth_header, params={'output_mode': 'json'})

    def async_get_shc_captain_info(self, auth_header):
        """
        Async api call to get /shcluster/captain/info
        :param auth_header:
        :return:
        """
        uri = '%s/services/shcluster/captain/info' % rest.makeSplunkdUri()
        return self.async_get_request(uri=uri, auth_header=auth_header, params={'output_mode': 'json'})

    @defer.inlineCallbacks
    def async_is_shc_member(self, auth_header):
        """
        Async helper method to determine if server is a search head cluster member
        :param auth_header:
        :return:
        """
        response = yield self.async_get_server_info(auth_header)

        if response.code == http.OK:
            json = yield response.json()
            server_roles = json['entry'][0]['content']['server_roles']
            for sh in ['shc_member', 'shc_captain']:
                if sh in server_roles:
                    defer.returnValue(True)
        defer.returnValue(False)

    @defer.inlineCallbacks
    def async_is_captain(self, auth_header):
        """
        Async helper method to determine if server is a search head cluster captain
        :param auth_header:
        :return:
        """
        response = yield self.async_get_server_info(auth_header)

        if response.code == http.OK:
            json = yield response.json()
            server_roles = json['entry'][0]['content']['server_roles']
            if 'shc_captain' in server_roles:
                defer.returnValue(True)
        defer.returnValue(False)

    @defer.inlineCallbacks
    def async_is_captain_ready(self, auth_header):
        """
        Async helper method to determine if search head cluster captain has been elected
        :param auth_header:
        :return:
        """
        response = yield self.async_get_shc_captain_info(auth_header)

        if response.code == http.OK:
            json = yield response.json()
            content = json['entry'][0]['content']
            if content['service_ready_flag'] and not content['maintenance_mode']:
                defer.returnValue(True)
        defer.returnValue(False)

