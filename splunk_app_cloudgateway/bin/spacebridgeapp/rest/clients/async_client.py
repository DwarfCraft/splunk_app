"""
(C) 2019 Splunk Inc. All rights reserved.

Base class for AsyncClient
"""
import sys
from spacebridgeapp.rest.clients.proxy_connect_agent import HTTPProxyConnector
from twisted.web.iweb import IPolicyForHTTPS
from twisted.internet import reactor
from zope.interface import implementer
from treq.client import HTTPClient
from twisted.web.client import Agent
from twisted.internet.ssl import CertificateOptions

from spacebridgeapp.util.config import cloudgateway_config
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, HEADER_AUTHORIZATION, \
    HEADER_CONTENT_TYPE, APPLICATION_JSON
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.string_utils import encode_whitespace

LOGGER = setup_logging("{}_async.log".format(SPACEBRIDGE_APP_NAME), "async_client")

# Default Base Timeout
DEFAULT_TIMEOUT = cloudgateway_config.get_async_timeout_secs()


def noverify_treq_instance(https_proxy=None):
    """
    Get an instance of the treq HTTP client that does not do hostname validation on HTTPS
    :return:
    """
    @implementer(IPolicyForHTTPS)
    class NoVerifyContextFactory(object):
        """
        Context Factory which does not validate hostname for HTTPS
        """

        def creatorForNetloc(self, hostname, port):
            return CertificateOptions(verify=False)

    # Setup of agent
    if https_proxy:
        host = https_proxy['host']
        port = https_proxy['port']

        proxy = HTTPProxyConnector(proxy_host=host,
                                   proxy_port=int(port))
        agent = Agent(reactor=proxy, contextFactory=NoVerifyContextFactory())
    else:
        agent = Agent(reactor, contextFactory=NoVerifyContextFactory())

    return HTTPClient(agent)


class AsyncClient(object):
    """
    Client for handling asynchronous requests to KV Store
    """

    def __init__(self, treq=noverify_treq_instance()):
        """
        Our client wraps the treq http client. This is so we can provide different implementations such as providing
        a mocked implementation to make testing easier.
        :param treq: instance of treq http client
        """
        self.treq = treq

    def async_get_request(self, uri, auth_header, params=None, headers=None, timeout=DEFAULT_TIMEOUT):
        """
        Makes a asynchronous get request to a given uri
        :param uri: string representing uri to make request to
        :param params: Optional parameters to be append as the query string to the URL
        :param auth_header: A value to supply for the Authorization header
        :param headers: Optional request headers
        :param timeout: Optional timeout
        :return: result of get request
        """

        uri = encode_whitespace(uri)

        if not headers:
            headers = {HEADER_CONTENT_TYPE: APPLICATION_JSON}

        if auth_header is not None:
            headers[HEADER_AUTHORIZATION] = repr(auth_header)

        LOGGER.debug('GET uri=%s, params=%s' % (uri, str(params)))

        uri = unicode(uri)

        return self.treq.get(url=uri,
                             headers=headers,
                             params=params,
                             timeout=timeout)

    def async_post_request(self, uri, auth_header, params=None, data=None, headers=None, timeout=DEFAULT_TIMEOUT):
        """
        Makes a asynchronous post request to a given uri
        :param uri: string representing uri to make request to
        :param params: Optional parameters to be append as the query string to the URL
        :param data: Request body
        :param auth_header: A value to supply for the Authorization header
        :param headers: header to send with post request.
        :param timeout: Optional timeout
        :return:
        """

        uri = encode_whitespace(uri)

        if not headers:
            headers = {HEADER_CONTENT_TYPE: APPLICATION_JSON}

        if auth_header is not None:
            headers[HEADER_AUTHORIZATION] = repr(auth_header)

        # In python 3 Treq requires post data to be bytes not string so we need to explicitly encode it
        # https://github.com/twisted/treq/issues/151
        if sys.version_info >= (3,0) and isinstance(data, str):
            data = data.encode('utf-8')

        # don't log request data as username and passwords can be leaked in plaintext MSB-846
        LOGGER.debug('POST uri=%s, params=%s', uri, params)

        uri = unicode(uri)

        return self.treq.post(url=uri,
                              headers=headers,
                              params=params,
                              data=data,
                              timeout=timeout)

    def async_delete_request(self, uri, auth_header, params=None, timeout=DEFAULT_TIMEOUT):
        """
        :param uri:
        :param params:
        :param auth_header: A value to supply for the Authorization header
        :param timeout: Optional timeout
        :return:
        """

        headers = {HEADER_CONTENT_TYPE: APPLICATION_JSON, HEADER_AUTHORIZATION: repr(auth_header)}
        LOGGER.debug('DELETE uri=%s, params=%s' % (uri, str(params)))

        uri = unicode(uri)

        return self.treq.delete(url=uri,
                                headers=headers,
                                params=params,
                                timeout=timeout)
