import json
import pickle
import random

from cloudgateway.device import EncryptionKeys
from cloudgateway.encryption_context import EncryptionContext
from cloudgateway.private.sodium_client import SodiumClient
from spacebridgeapp.rest.clients.async_client_factory import AsyncClientFactory
from spacebridgeapp.subscriptions.subscription_processor import process_pubsub_subscription
from spacebridgeapp.util import py23

from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from twisted.internet import defer, reactor
from twisted.internet.protocol import ProcessProtocol

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + '_process_manager.log', 'process_manager')


class JobContext(object):
    def __init__(self, auth_header, splunk_uri, encryption_keys, search_context=None):
        self.auth_header = auth_header
        self.splunk_uri = splunk_uri
        self.encryption_keys = encryption_keys
        self.search_context = search_context

    def with_search(self, search_context):
        return JobContext(self.auth_header, self.splunk_uri, self.encryption_keys, search_context)


def _partition(job_contexts, n_groups):
    # so that the same subscriptions aren't always grouped together
    random.shuffle(job_contexts)
    partioned_contexts = []
    for i in range(n_groups):
        partioned_contexts.append([])

    for i in range(len(job_contexts)):
        group_idx = i % n_groups
        partioned_contexts[group_idx].append(job_contexts[i])

    return partioned_contexts


class SearchProcess(ProcessProtocol):
    def __init__(self, job_contexts):
        self.deferred = defer.Deferred()
        self.pid = None
        self.job_contexts = job_contexts

    def processEnded(self, reason):
        rc = reason.value.exitCode
        if rc == 0:
            LOGGER.debug("processEnded, pid=%d, status=%s", self.pid, rc)
            self.deferred.callback(self)
        else:
            LOGGER.debug("processEnded, pid=%d, error=%s", self.pid, reason)
            self.deferred.errback(rc)

    def connectionMade(self):
        encoded = py23.b64encode_to_str(pickle.dumps(self.job_contexts))
        self.transport.write(encoded)
        self.transport.write("\n")


def start_job_using_subprocess(command, args):
    def executor(job_contexts):
        protocol = SearchProcess(job_contexts)
        p = reactor.spawnProcess(protocol, command, args)
        protocol.pid = p.pid
        return protocol

    return executor


class FakeProcess(object):
    def __init__(self, deferred):
        self.pid = -1
        self.deferred = deferred


def start_job_single_process(sodium_client, encryption_context):
    def executor(job_contexts):
        deferreds = []
        for job in job_contexts:
            LOGGER.debug("Processing search job. search_key=%s", job.search_context.search.key())
            async_client_factory = AsyncClientFactory(job.splunk_uri)
            d = process_pubsub_subscription(job.auth_header, encryption_context,
                                            async_client_factory.spacebridge_client(),
                                            async_client_factory.kvstore_client(),
                                            async_client_factory.splunk_client(), job.search_context)
            deferreds.append(d)

        return FakeProcess(defer.DeferredList(deferreds, consumeErrors=True))
    return executor


class ProcessManager(object):

    def __init__(self, num_processes, search_process_fn):
        self.num_processes = num_processes
        self.search_process_fn = search_process_fn

    @defer.inlineCallbacks
    def delegate(self, tag, job_contexts):
        running_processes = []
        pid_group = []
        paritioned_contexts = _partition(job_contexts, self.num_processes)

        LOGGER.debug("Distributing jobs to workers. jobs=%s, workers=%s, category=%s", len(job_contexts),
                     self.num_processes, tag)

        for context in paritioned_contexts:
            if len(context) == 0:
                continue
            process = self.search_process_fn(context)
            pid_group.append(process.pid)
            running_processes.append(process.deferred)
            LOGGER.debug("Process started, pid=%s", process.pid)

        yield defer.DeferredList(running_processes, consumeErrors=True)

        LOGGER.debug("Processing complete, pids=%s, category=%s", pid_group, tag)















