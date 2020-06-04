"""
(C) 2020 Splunk Inc. All rights reserved.

Module to manage Drone Mode Subscriptions
"""
from twisted.internet import reactor, defer
from twisted.web import http
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants

from spacebridgeapp.drone_mode.drone_mode_subscription_requests import (
    build_tv_subscription_updates,
    send_updates,
    fetch_subscriptions,
    build_ipad_subscription_updates,
    check_for_dead_captains)
from spacebridgeapp.drone_mode.drone_mode_utils import get_drone_mode_users, clean_up_orphaned_configs


from spacebridgeapp.request.splunk_auth_header import SplunkAuthHeader
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.rest.load_balancer_verification import get_uri
from spacebridgeapp.rest.clients.async_client_factory import AsyncClientFactory
from spacebridgeapp.rest.clients.async_spacebridge_client import AsyncSpacebridgeClient
from spacebridgeapp.messages.request_context import RequestContext


LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + '_drone_mode_subscription_manager.log',
                       'drone_mode_subscription_manager')


class DroneModeSubscriptionManager(object):

    def __init__(self, input_config, encryption_context, session_key, async_splunk_client,
                 parent_process_monitor=None,
                 cluster_monitor=None,
                 async_client_factory=None,
                 async_kvstore_client=None,
                 async_spacebridge_client=AsyncSpacebridgeClient()):
        """
        Subscription Manager constructor
        :param input_config:
        :param encryption_context:
        :param session_key:
        :param async_kvstore_client:
        :param async_splunk_client:
        :param async_spacebridge_client:
        """
        self.input_config = input_config
        self.encryption_context = encryption_context
        self.session_key = session_key
        self.parent_process_monitor = parent_process_monitor
        self.cluster_monitor = cluster_monitor
        self.async_splunk_client = async_splunk_client
        self.async_spacebridge_client = async_spacebridge_client
        self.system_auth_header = SplunkAuthHeader(self.session_key)
        if not async_client_factory:
            uri = get_uri(self.session_key)
            async_client_factory = AsyncClientFactory(uri)
        self.async_client_factory = async_client_factory
        if not async_kvstore_client:
            async_kvstore_client = self.async_client_factory.kvstore_client()
        self.async_kvstore_client = async_kvstore_client
        self.request_context = RequestContext(auth_header=self.system_auth_header,
                                              current_user=constants.ADMIN,
                                              system_auth_header=self.system_auth_header)

    @defer.inlineCallbacks
    def update_subscribers(self):
        """
        Run Loop to process drone mode tv and ipad subscriptions, loops every 10 seconds.
        :return:
        """

        try:
            LOGGER.debug("Running drone mode subscription manager")
            response_code, drone_mode_users = yield get_drone_mode_users(self.async_client_factory, self.system_auth_header)
            if response_code != http.OK:
                raise SpacebridgeApiRequestError('unable to fetch user list while checking for drone mode subscriptions',
                                                 status_code=response_code)

            LOGGER.debug('drone_mode_users=%s', drone_mode_users)
            drone_mode_subscriptions = yield fetch_subscriptions(self.system_auth_header,
                                                                 self.async_kvstore_client,
                                                                 user_list=drone_mode_users
                                                                 )

            yield clean_up_orphaned_configs(self.request_context,
                                            self.async_kvstore_client)
            yield check_for_dead_captains(self.request_context,
                                          self.async_kvstore_client,
                                          drone_mode_users)

            # Send tv + ipad updates
            tv_subscriptions = []
            ipad_subscriptions = []
            for subscription in drone_mode_subscriptions:
                if subscription.subscription_type == constants.DRONE_MODE_TV:
                    tv_subscriptions.append(subscription)
                if subscription.subscription_type == constants.DRONE_MODE_IPAD:
                    ipad_subscriptions.append(subscription)

            if tv_subscriptions:
                # build tv subcription updates
                tv_subscription_tuples = yield build_tv_subscription_updates(tv_subscriptions,
                                                                             self.request_context,
                                                                             self.async_kvstore_client)
                # send tv subscription_updates
                yield send_updates(tv_subscription_tuples,
                                   self.encryption_context,
                                   self.async_client_factory,
                                   self.request_context,
                                   constants.DRONE_MODE_TV)

            if ipad_subscriptions:
                # build ipad_subscription_updates
                ipad_subscription_tuples = yield build_ipad_subscription_updates(ipad_subscriptions,
                                                                                 self.request_context,
                                                                                 self.async_kvstore_client)

                # send tv subscription_updates
                yield send_updates(ipad_subscription_tuples,
                                   self.encryption_context,
                                   self.async_client_factory,
                                   self.request_context,
                                   constants.DRONE_MODE_IPAD)

        except Exception as e:
            LOGGER.exception("An error occurred updating drone mode subscribers")
            raise e

    def run(self):
        """
        Main Execute loop for Subscription Manager

        """
        d = self.update_subscribers()

        # Once run_loop has processed all it's iterations we kill the modular_input
        d.addCallback(lambda _: reactor.stop())
        d.addErrback(lambda _: reactor.stop())

        # Start cluster monitor
        if self.cluster_monitor is not None:
            self.cluster_monitor.monitor(self.system_auth_header, reactor)

        # Kickoff Main Event loop
        reactor.run()
