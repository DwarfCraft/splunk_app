from autobahn.twisted.websocket import WebSocketClientFactory, connectWS
from cloudgateway.private.registration.util import sb_auth_header
from cloudgateway.private.util.splunk_auth_header import SplunkAuthHeader
from cloudgateway.private.websocket import cloudgateway_client_protocol
from cloudgateway.private.messages.cloudgateway_message_handler import CloudgatewayMessageHandler
from twisted.internet.protocol import ReconnectingClientFactory
from cloudgateway.private.util import constants
from twisted.internet import reactor
from threading import Thread


class CloudgatewayClientFactory(WebSocketClientFactory, ReconnectingClientFactory):
    """
    Client factory implementation to handle autoreconnect on connection fail or loss
    """

    def configure(self, client_protocol,  max_reconnect_delay):
        self.protocol = client_protocol
        self.maxDelay = int(max_reconnect_delay)

    def clientConnectionFailed(self, connector, reason):
        self.retry(connector)

    def clientConnectionLost(self, connector, reason):
        self.retry(connector)

    def retry(self, connector=None):
        super(CloudgatewayClientFactory, self).retry(connector)


class CloudgatewayConnector(object):
    """
    Abstract class used to initiate a connection to cloudgateway via websocket. This is abstract because there are
    different methods by which we may want to connect to Cloudgateway.
    """

    def __init__(self,
                 message_handler,
                 encryption_context,
                 system_session_key,
                 parent_process_monitor,
                 cluster_monitor,
                 logger,
                 config,
                 max_reconnect_delay=60,
                 mode=constants.THREADED_MODE,
                 threadpool_size=None,
                 shard_id=None
                 ):
        """
        Args:
            message_handler: IMessageHandler interface for delegating messages
            encryption_context: EncryptionContext object
            system_session_key: SplunkAuthHeader
            parent_process_monitor: ParentProcessMonitor
            logger: Logger object for logging purposes
            max_reconnect_delay: optional parameter to specify how long to wait before attempting to reconnect
        """
        self.message_handler = message_handler
        self.encryption_context = encryption_context
        self.system_session_key = system_session_key
        self.parent_process_monitor = parent_process_monitor
        self.cluster_monitor = cluster_monitor
        self.logger = logger
        self.max_reconnect_delay = max_reconnect_delay
        self.mode = mode
        self.config = config
        self.shard_id = shard_id

        if threadpool_size and mode == constants.THREADED_MODE:
            reactor.suggestThreadPoolSize(threadpool_size)

        if parent_process_monitor:
            self.logger.info("parent pid {}".format(parent_process_monitor.parent_pid))

    def build_client_factory(self):
        """
        Setup a cloudgatewayclientfactory object before a connection is established to Cloudgateway. Configures
        things like the uri to connect on, auth headers, websocket protocol options, etc.

        Returns: CloudgatewayClientFactory object

        """

        headers = {'Authorization': sb_auth_header(self.encryption_context)}

        if self.shard_id:
            headers[constants.HEADER_SHARD_ID] = self.shard_id
            self.logger.info("Using shard_id={}".format(self.shard_id))

        ws_url = "wss://{0}/deployment".format(self.config.get_spacebridge_server())
        proxy, auth = self.config.get_ws_https_proxy_settings()

        if auth:
            headers['Proxy-Authorization'] = 'Basic ' + auth

        factory = CloudgatewayClientFactory(ws_url, headers=headers, proxy=proxy)
        factory.configure(cloudgateway_client_protocol.SpacebridgeWebsocketProtocol, self.max_reconnect_delay)
        factory.setProtocolOptions(autoFragmentSize=65536)
        factory.protocol.encryption_context = self.encryption_context
        factory.protocol.system_auth_header = SplunkAuthHeader(self.system_session_key)
        factory.protocol.parent_process_monitor = self.parent_process_monitor
        factory.protocol.logger = self.logger
        factory.protocol.mode = self.mode
        factory.protocol.cluster_monitor = self.cluster_monitor
        return factory

    def connect(self):
        """
        Initiate a websocket connection to cloudgateway and kickoff the twisted reactor event loop.
        Returns:

        """
        factory = self.build_client_factory()
        async_message_handler = CloudgatewayMessageHandler(self.message_handler,
                                                           self.encryption_context,
                                                           self.logger)

        factory.protocol.message_handler = async_message_handler

        connectWS(factory)

        if self.mode == constants.THREADED_MODE:
            Thread(target=reactor.run, args=(False,)).start()
        else:
            reactor.run()



