#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Splunk specific dependencies
import sys

from splunk.clilib.bundle_paths import make_splunkhome_path
from spacebridgeapp.util import py23


from spacebridgeapp.util.config import cloudgateway_config as config
from spacebridgeapp.rest.clients.async_client import AsyncClient, noverify_treq_instance
from splunklib.searchcommands import dispatch, GeneratingCommand, Configuration, Option, validators
from twisted.internet import reactor


class EchoState(object):
    def __init__(self):
        self.ok = False
        self.message = ''


@Configuration(type='reporting')
class CloudgatewayAsyncCheck(GeneratingCommand):
    """
    This command checks spacebridge reachability by using twisted to make an http call to the health check endpoint.
    Any http return other than 200 is considered a failure.  By default it will inherit Splunk's proxy settings and use
    them.  In the command you can disable the proxy by passing useProxy=False.
    """
    useProxy = Option(require=False, validate=validators.Boolean(), default=True)

    def __init__(self):
        super(CloudgatewayAsyncCheck, self).__init__()
        self.echo_state = EchoState()

    def run(self):
        proxy = config.get_https_proxy_settings()
        uri = "{}/health_check".format(config.get_spacebridge_domain())

        if not self.useProxy:
            proxy = None

        client = AsyncClient(treq=noverify_treq_instance(https_proxy=proxy))

        def done(result):
            if result.code == 200:
                self.echo_state.ok = True
            else:
                self.echo_state.message = 'Got http {}'.format(result.code)
            reactor.stop()

        def err(failure):
            self.echo_state.message = failure
            reactor.stop()

        d = client.async_get_request(uri, None)
        d.addCallback(done)
        d.addErrback(err)

        reactor.run()
        return {'https_async': self.echo_state.ok, 'message': self.echo_state.message}

    def generate(self):
        yield self.run()

    ''' HELPERS '''

dispatch(CloudgatewayAsyncCheck, sys.argv, sys.stdin, sys.stdout, __name__)
