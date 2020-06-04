#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Splunk specific dependencies
import sys

from splunk.clilib.bundle_paths import make_splunkhome_path
from spacebridgeapp.util import py23


from twisted.internet import reactor
from splunklib.searchcommands import dispatch, GeneratingCommand, Configuration, Option, validators
from spacebridgeapp.util.config import cloudgateway_config as config
from autobahn.twisted.websocket import WebSocketClientFactory, connectWS, WebSocketClientProtocol

# Command specific dependencies
import uuid


class EchoState(object):
    def __init__(self):
        self.payload = str(uuid.uuid4())
        self.ok = False
        self.message = ''


class CheckMobileWssProtocol(WebSocketClientProtocol):
    def onConnect(self, response):
        self.sendMessage(self.factory.state.payload, isBinary=True)

    def onMessage(self, payload, isBinary):
        expected = self.factory.state.payload
        match = (payload == expected)
        self.factory.state.ok = match
        if not match:
            self.factory.state.message = 'Received unknown message'
        reactor.stop()

@Configuration(type='reporting')
class CloudgatewayHttpsCheck(GeneratingCommand):
    """
    This command checks spacebridge reachability by using twisted to connect to the websocket echo endpoint and sending
    a message.  The test is considered a success if it gets back the message it sent within 10 seconds.
    By default it will inherit Splunk's proxy settings and use them.  In the command you can disable the proxy by
    passing useProxy=False.
    """
    useProxy = Option(require=False, validate=validators.Boolean(), default=True)

    def __init__(self):
        super(CloudgatewayHttpsCheck, self).__init__()
        self.echo_state = EchoState()

    def timeout(self):
        self.echo_state.message = 'Timeout'
        reactor.stop()

    def test_wss(self):
        ws_url = "wss://{}/echo".format(config.get_spacebridge_server())

        headers = {'Authorization': "f00d"}

        use_proxy = self.useProxy

        proxy, auth = config.get_ws_https_proxy_settings()

        if use_proxy:
            # Proxy setup
            if auth:
                headers['Proxy-Authorization'] = 'Basic ' + auth
        else:
            proxy = None

        factory = WebSocketClientFactory(ws_url, headers=headers, proxy=proxy)
        factory.protocol = CheckMobileWssProtocol
        factory.state = self.echo_state

        connectWS(factory)

        reactor.callLater(10, self.timeout)

        reactor.run()

        record = {'websocket': self.echo_state.ok, 'message': self.echo_state.message}
        return record

    def generate(self):
        record = self.test_wss()

        yield record


dispatch(CloudgatewayHttpsCheck, sys.argv, sys.stdin, sys.stdout, __name__)
