"""
(C) 2019 Splunk Inc. All rights reserved.

Module for representation of data objects for ar assets
"""
import json
import os

from spacebridgeapp.ar.data.data_class_mixin import DataClassMixin
from spacebridgeapp.ar.rest.common import parse_asset_objects
from spacebridgeapp.util.constants import (
    USER_PROVIDED, SPLUNK_GENERATED, ASSET_NAME, ASSET_OBJECTS, ASSET_TYPE, KEY, ASSET_GROUP, AR_WORKSPACE_ID_KEY,
    DASHBOARD_ID_KEY
)

from splapp_protocol import augmented_reality_pb2, common_pb2
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'


class AssetData(DataClassMixin):
    """An AR Asset"""

    def __init__(self,
                 asset_name,
                 asset_id=None,
                 asset_group=None,
                 is_splunk_generated=False,
                 dashboard_description_pb=None,
                 ar_workspace_data_pb=None):
        self.asset_id = asset_id
        self.asset_name = asset_name
        self.asset_group = asset_group
        self.is_splunk_generated = is_splunk_generated
        if self.is_splunk_generated:
            self.asset_type = SPLUNK_GENERATED
        else:
            self.asset_type = USER_PROVIDED

        self.workspace = ar_workspace_data_pb or augmented_reality_pb2.ARWorkspaceData()
        self.dashboard = dashboard_description_pb or common_pb2.DashboardDescription()

    @staticmethod
    def from_json(asset_json):
        asset_object = {}
        if ASSET_OBJECTS in asset_json:
            asset_objects = parse_asset_objects(asset_json[ASSET_OBJECTS])
            if asset_objects:
                asset_object = asset_objects[0]

        workspace = augmented_reality_pb2.ARWorkspaceData()
        if AR_WORKSPACE_ID_KEY in asset_object:
            workspace.arWorkspaceId = asset_object[AR_WORKSPACE_ID_KEY]

        dashboard = common_pb2.DashboardDescription()
        if DASHBOARD_ID_KEY in asset_object:
            dashboard.dashboardId = asset_object[DASHBOARD_ID_KEY]

        return AssetData(
            asset_id=asset_json[KEY],
            asset_name=asset_json[ASSET_NAME],
            asset_group=asset_json.get(ASSET_GROUP),
            is_splunk_generated=asset_json[ASSET_TYPE] == SPLUNK_GENERATED,
            ar_workspace_data_pb=workspace,
            dashboard_description_pb=dashboard
        )

    def to_json(self, jsonify_objects=True, **kwargs):
        return json.dumps(self.to_dict(jsonify_objects), **kwargs)

    def to_dict(self, jsonify_objects=False):
        asset = {
            ASSET_NAME: self.asset_name,
            ASSET_TYPE: self.asset_type,
        }
        if self.asset_id:
            asset[KEY] = self.asset_id
        if self.asset_group:
            asset[ASSET_GROUP] = self.asset_group

        asset_details = {}
        if self.dashboard_id:
            asset_details[DASHBOARD_ID_KEY] = self.dashboard_id
        if self.workspace_id:
            asset_details[AR_WORKSPACE_ID_KEY] = self.workspace_id

        if asset_details and not self.asset_group:
            asset[ASSET_OBJECTS] = json.dumps([asset_details]) if jsonify_objects else [asset_details]

        return asset

    def set_protobuf(self, asset_data_pb):
        """Merges the data from this AssetData into the given augmented_reality_pb2.AssetData."""
        if self.asset_id:
            asset_data_pb.assetId = self.asset_id
        asset_data_pb.isSplunkGenerated = self.is_splunk_generated
        asset_data_pb.assetName = self.asset_name

        asset_data_object = augmented_reality_pb2.AssetDataObject()
        if self.workspace_id and self.dashboard_id:
            asset_data_object.arWorkspaceAsset.dashboard.CopyFrom(self.dashboard)
            asset_data_object.arWorkspaceAsset.workspaceData.CopyFrom(self.workspace)
        elif self.dashboard_id:
            asset_data_object.dashboardAsset.dashboard.CopyFrom(self.dashboard)

        del asset_data_pb.objects[:]
        asset_data_pb.objects.extend([asset_data_object])

    def to_protobuf(self):
        """Build protobuf from class

        :return: AssetData proto
        """
        proto = augmented_reality_pb2.AssetData()
        self.set_protobuf(proto)
        return proto

    @property
    def dashboard_id(self):
        return self.dashboard.dashboardId or None

    @property
    def workspace_id(self):
        return self.workspace.arWorkspaceId or None

    def __repr__(self):
        return self.to_json(indent=2, sort_keys=True)
