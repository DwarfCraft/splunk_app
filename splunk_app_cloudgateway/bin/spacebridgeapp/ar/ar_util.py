"""
(C) 2019 Splunk Inc. All rights reserved.
"""

import base64

from spacebridgeapp.util.py23 import py2_check_unicode
from splapp_protocol import augmented_reality_pb2
from twisted.internet import defer


def build_cloned_workspace_proto(workspace_base64_str, dashboard_id):
    """
    Given a base 64 string representing an AR workspace proto object, return an AR workspace proto object which is
    a copy of the input object but with the dashboard ids all changed to match the input dashboard id. This needs
    to happen at the top level of the object as well as for each child in the AR workspace object.
    """
    old_dashboard_workspace = base64.b64decode(workspace_base64_str)
    ar_workspace = augmented_reality_pb2.ARWorkspace()
    ar_workspace.ParseFromString(old_dashboard_workspace)
    ar_workspace.dashboardId = dashboard_id

    if ar_workspace.children and len(ar_workspace.children) > 0:
        for i in range(len(ar_workspace.children)):
            ar_workspace.children[i].dashboardVisualizationId.dashboardId = dashboard_id

    return ar_workspace


def create_empty_proto(dashboard_id):
    """
    return empty workspace object for a particular dashboard id
    """
    ar_workspace = augmented_reality_pb2.ARWorkspace()
    ar_workspace.dashboardId = dashboard_id
    return ar_workspace


def is_non_string_iterable(obj):
    if isinstance(obj, str) or py2_check_unicode(obj):
        return False
    try:
        _ = iter(obj)
        return True
    except TypeError:
        return False


@defer.inlineCallbacks
def wait_for_all(deferred_tasks, raise_on_first_exception=False):
    """
    An alternative for defer.DeferredList.

    This is temporary since AR will be moving to py3 shortly. The default DeferredList behavior is complicated and error
    handling is annoying. This approach is similar to how asyncio handles waiting on multiple coroutines.

    This should only be used if the success of each task is independent of the success of all remaining tasks.

    :param deferred_tasks: defer.Deferred objects to wait on
    :param raise_on_first_exception: If True, this will raise the first exception from any of the underlying deferreds.
    :return: A list of results from waiting on the given deferred objects. Any exceptions raised from the pending
             deferred objects will be returned as part of the result it is up to the caller to determine how to handle
             them.
    """
    results = []
    for deferred in deferred_tasks:
        try:
            result = yield deferred
        except Exception as e:
            if raise_on_first_exception:
                raise e
            result = e
        results.append(result)
    defer.returnValue(results)
