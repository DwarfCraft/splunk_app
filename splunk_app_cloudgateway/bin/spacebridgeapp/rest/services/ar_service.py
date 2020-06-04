"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for accessing and setting kvstore records
"""

import sys
import json
import splunk
import splunk.rest as rest
from spacebridgeapp.dashboard.dashboard_helpers import shorten_dashboard_id_from_url
from splunk.clilib.bundle_paths import make_splunkhome_path
from spacebridgeapp.util import py23


from spacebridgeapp.util.constants import NOBODY
from spacebridgeapp.util import constants
from spacebridgeapp.rest.services.kvstore_service import KVStoreCollectionAccessObject as KvStore


def ar_dashboard_exists(authtoken, dashboard_name):
    """
    Checks if a dashboard exists by searching the kvstore for it. Returns True or False.
    """
    kvstore = KvStore(constants.AR_DASHBOARDS_COLLECTION_NAME, authtoken, owner=NOBODY)
    try:
        kvstore.get_item_by_key(dashboard_name)
    except splunk.RESTException as err:
        if err.statusCode == 404:
            return False
        raise err
    return True


def post_dashboard_endpoint(authtoken, uri, contents):
    """
    Make a POST request to the Splunk dashboards REST API, creating or updating
    the specified dashboard and returning the integrity hash of the xml
    """

    r, dashboard_res = rest.simpleRequest(
        uri,
        sessionKey=authtoken,
        method='POST',
        getargs={'output_mode': 'json'},
        postargs=contents,
        raiseAllErrors=True
    )
    dashboard_res = json.loads(dashboard_res)
    integrity_hash = dashboard_res['entry'][0]['content']['eai:digest']
    # Return short form of the dashboard_id after creating (i.e. admin/splunk_app_cloudgateway/dashboard_name)
    dashboard_id = shorten_dashboard_id_from_url(dashboard_res['entry'][0]['id'])
    return integrity_hash, dashboard_id


def delete_dashboard_endpoint(authtoken, uri, dashboard_name):
    """
    Make a DELETE request to the Splunk dashboards REST API, deleting
    the specified dashboard
    """

    return rest.simpleRequest(
        '%s/%s' % (uri, dashboard_name),
        sessionKey=authtoken,
        method='DELETE',
        raiseAllErrors=True
    )
