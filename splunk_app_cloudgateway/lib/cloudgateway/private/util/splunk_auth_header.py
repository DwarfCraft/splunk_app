"""
(C) 2019 Splunk Inc. All rights reserved.
"""

from twisted.internet import defer
from twisted.web import http


class SplunkAuthHeader(object):
    def __init__(self, session_token):
        self.session_token = session_token

    def __repr__(self):
        return 'Splunk {0}'.format(self.session_token)

    @defer.inlineCallbacks
    def validate(self, async_splunk_client):
        """
        Validate this auth_header
        """
        response = yield async_splunk_client.async_get_current_context(auth_header=self)
        if response.code == http.OK:
            defer.returnValue(True)
        defer.returnValue(False)
