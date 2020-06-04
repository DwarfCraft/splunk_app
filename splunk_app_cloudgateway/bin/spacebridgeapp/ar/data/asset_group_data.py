"""
(C) 2020 Splunk Inc. All rights reserved.

Data class representing an AssetGroup
"""
import json

from spacebridgeapp.ar.data.data_class_mixin import DataClassMixin
from spacebridgeapp.ar.rest.common import parse_asset_objects
from spacebridgeapp.util.constants import (
    KEY, ASSET_GROUP_NAME, ASSET_GROUP_OBJECTS, AR_WORKSPACE_ID_KEY, DASHBOARD_ID_KEY
)


class AssetGroup(DataClassMixin):

    def __init__(self, name, dashboard_id, key=None, workspace_id=None):
        self.asset_group_id = key
        self.asset_group_name = name
        self.dashboard_id = dashboard_id
        self.workspace_id = workspace_id

    @staticmethod
    def from_json(asset_group_json):
        asset_group_object = {}
        if ASSET_GROUP_OBJECTS in asset_group_json:
            asset_group_objects = parse_asset_objects(asset_group_json[ASSET_GROUP_OBJECTS])
            if asset_group_objects:
                asset_group_object = asset_group_objects[0]

        return AssetGroup(
            name=asset_group_json[ASSET_GROUP_NAME],
            key=asset_group_json.get(KEY),
            dashboard_id=asset_group_object.get(DASHBOARD_ID_KEY),
            workspace_id=asset_group_object.get(AR_WORKSPACE_ID_KEY)
        )

    def to_dict(self, jsonify_objects=False):
        asset_group = {ASSET_GROUP_NAME: self.asset_group_name}
        if self.asset_group_id:
            asset_group[KEY] = self.asset_group_id

        asset_group_object = {}
        if self.dashboard_id:
            asset_group_object[DASHBOARD_ID_KEY] = self.dashboard_id
        if self.workspace_id:
            asset_group_object[AR_WORKSPACE_ID_KEY] = self.workspace_id

        if asset_group_object:
            asset_group[ASSET_GROUP_OBJECTS] = (json.dumps([asset_group_object])
                                                if jsonify_objects else [asset_group_object])
        return asset_group

    def to_json(self, jsonify_objects=True, **kwargs):
        return json.dumps(self.to_dict(jsonify_objects=jsonify_objects), **kwargs)

    def __hash__(self):
        return hash(self.asset_group_id)

    def __repr__(self):
        return self.to_json(jsonify_objects=False, indent=2, sort_keys=True)
