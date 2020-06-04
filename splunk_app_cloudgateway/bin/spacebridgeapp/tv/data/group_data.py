"""
(C) 2019 Splunk Inc. All rights reserved.

Module to represent Group data object
"""

from splapp_protocol import common_pb2
from spacebridgeapp.data.base import SpacebridgeAppBase
from spacebridgeapp.util.type_to_string import to_utf8_str
from spacebridgeapp.tv.data.resource_type import ResourceType


class Group(SpacebridgeAppBase):
    """
    Object container for a Group object in kvstore
    """
    @staticmethod
    def from_json(json_obj):
        """
        Static initializer of Group object from a json object
        :param json_obj:
        :return: Group object
        """
        group = Group()
        if json_obj:
            group.name = json_obj.get('name', "")
            group.resource_type = int(json_obj.get('resource_type', ResourceType.INVALID.value))
            group.resource_ids = json_obj.get('resource_ids', [])
            group._user = json_obj.get('_user')
            group._key = json_obj.get('_key')
        return group

    @staticmethod
    def from_proto(proto):
        """
        Static initializer of Group object from a proto object
        :param proto:
        :return:
        """
        group = Group()
        if proto:
            group._key = proto.groupId
            group.name = proto.groupName
            group.resource_type = proto.resourceType
            group.resource_ids = proto.resourceIds
        return group

    def __init__(self,
                 name=None,
                 resource_type=None,
                 resource_ids=None,
                 _user='',
                 _key=''):
        self.name = name
        self.resource_type = resource_type
        self.resource_ids = resource_ids if resource_ids else []
        self._user = _user
        self._key = _key

    def __repr__(self):
        """
        Stringify the object
        :return:
        """
        return "group_id={}, user={}, group_name={}, resource_type={}, resource_ids={}"\
            .format(self._key, self._user, self.name, self.resource_type, self.resource_ids)

    def set_protobuf(self, proto):
        """Set proto attributes from class

        :param proto: {Group} protobuf object
        :return:
        """
        proto.groupId = self._key
        proto.groupName = self.name
        proto.resourceType = self.resource_type

        resource_id_list = [to_utf8_str(resource_id) for resource_id in self.resource_ids]
        del proto.resourceIds[:]
        proto.resourceIds.extend(resource_id_list)

    def to_protobuf(self):
        """Build protobuf from class

        :return: AssetData proto
        """
        proto = common_pb2.Group()
        self.set_protobuf(proto)
        return proto

    def key(self):
        return self._key

    def is_valid(self):
        """
        Helper method used in set to determine if Group object is valid
        :return:
        """
        resource_type_enum = ResourceType.from_value(self.resource_type)
        return self.name and resource_type_enum != ResourceType.INVALID and self.resource_ids
