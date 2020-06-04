"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for accessing and setting asset kvstore records
"""
import json
import sys

from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util.constants import (
    SPACEBRIDGE_APP_NAME, AR_WORKSPACE_ID_KEY, DASHBOARD_ID_KEY
)
from twisted.web import http


LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + ".log", "rest_asset")


def validate_asset_or_group_objects(asset_objects, new_workspace_title=None, asset_is_grouped=False):
    """Validates the given asset or asset group update parameters."""
    if new_workspace_title and any(AR_WORKSPACE_ID_KEY in obj for obj in asset_objects):
        raise SpacebridgeApiRequestError('Cannot provide a workspace title if you provide an existing workspace',
                                         status_code=http.BAD_REQUEST)

    if asset_is_grouped:
        return

    if not asset_objects:
        raise SpacebridgeApiRequestError('All requests must contain at least one asset object',
                                         status_code=http.BAD_REQUEST)
    if not all(DASHBOARD_ID_KEY in obj for obj in asset_objects):
        raise SpacebridgeApiRequestError('All asset objects must contain a dashboard ID',
                                         status_code=http.BAD_REQUEST)


def create_asset_objects(dashboard_id, workspace_id=None):
    ids = {DASHBOARD_ID_KEY: dashboard_id}
    if workspace_id:
        ids[AR_WORKSPACE_ID_KEY] = workspace_id
    return [ids]


def parse_asset_objects(asset_objects):
    if isinstance(asset_objects, list):
        return asset_objects
    return json.loads(asset_objects)
