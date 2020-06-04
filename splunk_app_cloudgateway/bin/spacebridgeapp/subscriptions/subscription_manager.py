"""
(C) 2019 Splunk Inc. All rights reserved.

Module to manage Subscriptions
"""
import time
from collections import defaultdict

from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from spacebridgeapp.rest.clients.async_kvstore_client import AsyncKvStoreClient
from twisted.internet import reactor, defer

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + '_subscription_manager.log', 'subscription_manager')


SEARCH_CATEGORY_STANDALONE = 'standalone'
SEARCH_CATEGORY_REF = 'ref'
SEARCH_CATEGORY_BASE = 'base'

PROCESS_CATEGORY_ORDER = [SEARCH_CATEGORY_STANDALONE, SEARCH_CATEGORY_REF, SEARCH_CATEGORY_BASE]


def _categorize_searches(search_bundle):
    categorized = defaultdict(list)
    for search in search_bundle.searches:
        cat = None
        if search.parent_search_key is None:
            cat = SEARCH_CATEGORY_STANDALONE
        elif search.ref:
            cat = SEARCH_CATEGORY_REF
        elif search.base:
            cat = SEARCH_CATEGORY_BASE
        categorized[cat].append(search_bundle.to_search_context(search.key()))
    return categorized


class SubscriptionManager(object):

    def __init__(self, input_config, encryption_context, auth_header,
                 minimum_iteration_time_seconds,
                 process_manager,
                 search_loader,
                 job_context,
                 warn_threshold_seconds=None,
                 parent_process_monitor=None,
                 shard_id=None,
                 async_kvstore_client=AsyncKvStoreClient()):
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
        self.parent_process_monitor = parent_process_monitor
        self.async_kvstore_client = async_kvstore_client
        self.system_auth_header = auth_header
        self.minimum_iteration_time_seconds = minimum_iteration_time_seconds
        self.warn_threshold_seconds = warn_threshold_seconds
        self.shard_id = shard_id
        self.process_manager = process_manager
        self.base_job_context = job_context
        self.load_searches = search_loader

    @defer.inlineCallbacks
    def _process(self):
        try:
            search_bundle = yield self.load_searches(self.system_auth_header, self.shard_id, self.async_kvstore_client)

            LOGGER.debug("Found active searches count=%d", len(search_bundle.searches))

            search_contexts = _categorize_searches(search_bundle)

            for category in PROCESS_CATEGORY_ORDER:
                job_contexts = [self.base_job_context.with_search(search_context)
                                for search_context in search_contexts[category]]
                yield self.process_manager.delegate(category, job_contexts)

            defer.returnValue(True)
        except Exception:
            LOGGER.exception("Failed to process")

    @defer.inlineCallbacks
    def _run_loop(self):
        LOGGER.debug("Starting pubsub iteration")
        start_time_seconds = time.time()
        try:
            yield self._process()
        except Exception as e:
            # if something has made its way up here, the only safe thing to do is shut down and wait for
            # Splunk to restart the process
            LOGGER.exception("Unexpected Error while processing subscriptions!")
            reactor.stop()
            return

        time_taken_seconds = time.time() - start_time_seconds

        if self.warn_threshold_seconds and self.warn_threshold_seconds < time_taken_seconds:
            LOGGER.warn("Subscription processing took time_seconds=%s, warn_threshold_seconds=%s",
                        time_taken_seconds, self.warn_threshold_seconds)

        LOGGER.debug("Subscriptions processed, time_taken=%s", time_taken_seconds)

        # if we've taken longer than the minimum, schedule immediately
        raw_delay_required = self.minimum_iteration_time_seconds - time_taken_seconds
        delay_required_seconds = max(raw_delay_required, 0)

        LOGGER.debug("Subscription loop will sleep for delay_seconds=%s", delay_required_seconds)

        reactor.callLater(delay_required_seconds, self._run_loop)

    def run(self):
        """
        Main Execute loop for Subscription Manager
        :return:
        """
        LOGGER.info("Starting run_loop...")
        self._run_loop()

        # Start parent_process_monitor
        if self.parent_process_monitor is not None:
            LOGGER.info("parent pid %s" % self.parent_process_monitor.parent_pid)
            self.parent_process_monitor.monitor(LOGGER, reactor)

        # Kickoff Main Event loop
        reactor.run()
