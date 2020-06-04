"""
(C) 2019 Splunk Inc. All rights reserved.

Util Module for functions requiring polling loops
"""

from twisted.internet import defer, reactor, task

DEFAULT_SEND_DATA_POLL_INTERVAL = 2
DEFAULT_SEND_DATA_TIMEOUT = 600

DEFAULT_JOB_RESULTS_POLL_INTERVAL = 1
DEFAULT_JOB_RESULTS_TIMEOUT = 60


class LoopReturn(object):
    def __init__(self, response=None, update_count=0):
        self.response = response
        self.update_count = update_count


@defer.inlineCallbacks
def deferred_loop(poll_interval_seconds=2, timeout_seconds=600, deferred_function=None, **kwargs):
    # short circuit if no function defined
    if not deferred_function:
        defer.returnValue(None)

    # loop to update search job status
    update_count = 0

    # Ensure we are acceptable values
    timeout_counter_seconds = timeout_seconds if timeout_seconds > 0 else DEFAULT_SEND_DATA_TIMEOUT
    poll_interval_seconds = poll_interval_seconds if poll_interval_seconds > 0 else DEFAULT_SEND_DATA_POLL_INTERVAL
    while timeout_counter_seconds > 0:
        # increment the update_count
        update_count += 1
        # run the deferred function
        result = yield deferred_function(**kwargs)

        # return result if not None, otherwise continue looping
        if result is not None:
            defer.returnValue(LoopReturn(result, update_count))
        # Sleep here until next interval
        yield task.deferLater(reactor, poll_interval_seconds, lambda: None)
        # Calculate timeout_counter_seconds value
        timeout_counter_seconds -= poll_interval_seconds
    defer.returnValue(LoopReturn(None, update_count))
