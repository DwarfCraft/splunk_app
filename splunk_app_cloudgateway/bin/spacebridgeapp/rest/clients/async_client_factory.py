"""
(C) 2019 Splunk Inc. All rights reserved.

Factory class to return async client types
"""

from spacebridgeapp.rest.clients.async_kvstore_client import AsyncKvStoreClient
from spacebridgeapp.rest.clients.async_splunk_client import AsyncSplunkClient
from spacebridgeapp.rest.clients.async_jubilee_client import AsyncJubileeClient
from spacebridgeapp.rest.clients.async_spacebridge_client import AsyncSpacebridgeClient
from spacebridgeapp.ar.permissions.async_permissions_client import AsyncArPermissionsClient
from spacebridgeapp.metrics.telemetry_client import AsyncTelemetryClient

# Value factory selectors
FACTORY = 'async_client_factory'
KVSTORE = 'async_kvstore_client'
SPLUNK = 'async_splunk_client'
JUBILEE = 'async_jubilee_client'
SPACEBRIDGE = 'async_spacebridge_client'
TELEMETRY = 'async_telemetry_client'
AR_PERMISSIONS = 'async_ar_permissions_client'


class AsyncClientFactory(object):

    def __init__(self, uri):
        """

        :param uri: string representing uri to make request to
        """
        self.uri = uri
        self.async_telemetry_client = AsyncTelemetryClient()

    def from_value(self, value):
        """
        Helper method to get async_client by value name
        :param value:
        :return:
        """
        if FACTORY == value:
            return self
        elif KVSTORE == value:
            return self.kvstore_client()
        elif SPLUNK == value:
            return self.splunk_client()
        elif JUBILEE == value:
            return self.jubilee_client()
        elif SPACEBRIDGE == value:
            return self.spacebridge_client()
        elif AR_PERMISSIONS == value:
            return self.ar_permissions_client()
        elif TELEMETRY == value:
            return self.telemetry_client()
        return None

    def kvstore_client(self):
        return AsyncKvStoreClient()

    def splunk_client(self):
        return AsyncSplunkClient(self.uri)

    def jubilee_client(self):
        return AsyncJubileeClient()

    def spacebridge_client(self):
        return AsyncSpacebridgeClient()

    def ar_permissions_client(self):
        return AsyncArPermissionsClient(self.splunk_client(), self.kvstore_client())

    def telemetry_client(self):
        return self.async_telemetry_client
