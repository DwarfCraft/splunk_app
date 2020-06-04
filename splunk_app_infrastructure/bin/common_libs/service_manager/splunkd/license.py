# Copyright 2016 Splunk Inc. All rights reserved.
# Environment configuration
# N/A
# Standard Python Libraries
import json
from future.moves.urllib.parse import urlencode
from future.moves.urllib.request import Request, urlopen
from future.moves.urllib.error import HTTPError
import http.client

from . import BaseSplunkdServiceManager


class LicenseManager(BaseSplunkdServiceManager):
    """
    License access
    """

    _licenses = None

    def __init__(self, server_uri, session_key, check_local_slave=False):
        """
        Return License Manager object

        :param server_uri: splunkd server uri
        :param session_key
        :param check_local_slave: set to true when the splunk instance that
               executes this code is a license slave. Should be set to true when it's a distributed deployment
        """
        super(LicenseManager, self).__init__(session_key, server_uri)
        self.check_local_slave = check_local_slave

    def base_uri(self):
        endpoint = 'localslave' if self.check_local_slave else 'licenses'
        return '{server_uri}/services/licenser/{endpoint}'.format(
            server_uri=self.server_uri,
            endpoint=endpoint
        )

    def _build_uri(self):
        """
        Create uri for license request
        return: uri for license request
        """
        qs = dict(output_mode='json')
        base_uri = self.base_uri()
        return '%s?%s' % (base_uri, urlencode(qs))

    def _build_send_req(self, url, method='GET'):
        h = {
            'Authorization': 'Splunk %s' % self.session_key,
            'Content-Type': 'application/json'
        }
        try:
            request = Request(url, headers=h)
            request.get_method = lambda: method
            response = urlopen(request)
            return json.loads(response.read())
        except HTTPError as e:
            if e.code == http.client.NOT_FOUND:
                return None
            else:
                raise e

    def load(self):
        # Return early if license data has already been retrieved
        if LicenseManager._licenses is not None:
            return LicenseManager._licenses
        url = self._build_uri()
        # Cache license data since it doesn't change without system restart
        LicenseManager._licenses = self._build_send_req(url, 'GET')
        return LicenseManager._licenses
