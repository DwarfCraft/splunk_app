"""
(C) 2019 Splunk Inc. All rights reserved.

Utilities for creating Splunk facing REST endpoints that use Twisted APIs and asynchronous code. Usage is similar to
base_endpoint.BaseRestHandler but instead of get, post, put, and delete, subclasses should override async_get,
async_post, async_put, and async_delete respectively.

Users of base_endpoint.BaseRestHandler should use async_base_endpoint.call(...) if migrating to
async_base_endpoint.AsyncBaseRestHandler is too much of an inconvenience but there is still a use case for getting a
result from asynchronous code.

Example usage:

class MyRestHandler(async_base_endpoint.AsyncBaseRestHandler):

    @defer.inlineCallbacks
    def async_get(self, request):
        some_async_result = yield some_async_method()
        defer.returnValue({
            'payload': some_async_result,
            'status': 200
        })

** NOTE **
Do not pass a deferred to defer.returnValue. This is not supported by Twisted, but more annoyingly, will cause an
infinite loop that will prevent your request from succeeding AND prevent you from manually stopping Splunk with the
splunk stop command line command. You will have to manually kill the process with something like:

    lsof -i tcp:8089
    kill -9 <process IDs from the previous command>
"""
import sys
import threading

from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from spacebridgeapp import logging
from spacebridgeapp.rest import base_endpoint
from spacebridgeapp.rest.clients.async_client_factory import AsyncClientFactory
from spacebridgeapp.util import constants
from splunk import rest
from splunk.persistconn import application
from twisted.internet import reactor
from twisted.internet import threads


LOGGER = logging.setup_logging(constants.SPACEBRIDGE_APP_NAME + '.log', 'async_bridge_v2')


def call(async_func, *args, **kwargs):
    """Executes an asynchronous function as a blocking call using the REST handler reactor."""
    _reactor_thread.wait_until_ready()
    return threads.blockingCallFromThread(reactor, async_func, *args, **kwargs)


class AsyncBaseRestHandler(base_endpoint.BaseRestHandler, application.PersistentServerConnectionApplication):
    """Base class for REST handlers that would like to use Twisted APIs to handle requests."""

    def __init__(self, command_line, command_arg, async_client_factory=None):
        # command_line and command_arg are passed in (but for some reason unused??) by the Splunk REST framework.
        # Accepting them at this level saves us from making all subclasses accept them.
        super(AsyncBaseRestHandler, self).__init__()
        self.async_client_factory = async_client_factory or AsyncClientFactory(rest.makeSplunkdUri())

    def handle_request(self, request):
        method = request['method']
        if method == 'GET':
            return call(self.async_get, request)
        elif method == 'POST':
            return call(self.async_post, request)
        elif method == 'PUT':
            return call(self.async_put, request)
        elif method == 'DELETE':
            return call(self.async_delete, request)
        return base_endpoint.unsupported_method_response(method)

    def async_get(self, request):
        return base_endpoint.unsupported_method_response('GET')

    def async_post(self, request):
        return base_endpoint.unsupported_method_response('POST')

    def async_put(self, request):
        return base_endpoint.unsupported_method_response('PUT')

    def async_delete(self, request):
        return base_endpoint.unsupported_method_response('DELETE')

    def handleStream(self, handle, in_string):
        # This isn't used by the Splunk REST framework yet but IDEs will generally complain if it isn't implemented by
        # subclasses of PersistentServerConnectionApplication.
        pass


class _ReactorThread(threading.Thread):

    def __init__(self):
        super(_ReactorThread, self).__init__(name='async_base_endpoint_reactor_thread')
        self.daemon = True
        self._reactor_started = threading.Event()

    def run(self):
        if reactor.running:
            self._notify_reactor_ready()
            return
        reactor.callWhenRunning(self._notify_reactor_ready)
        reactor.run(False)

    def wait_until_ready(self):
        self._reactor_started.wait()

    def _notify_reactor_ready(self):
        self._reactor_started.set()


# This is the per process reactor thread. All handlers that subclass AsyncBaseRestHandler use the same reactor as all
# other handlers in the same process.
_reactor_thread = _ReactorThread()
_reactor_thread.start()
