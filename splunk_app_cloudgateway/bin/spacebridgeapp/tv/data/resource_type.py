"""
(C) 2019 Splunk Inc. All rights reserved.

Enumeration object for ResourceType
"""

from enum import Enum


class ResourceType(Enum):
    INVALID = 0
    DASHBOARD = 1

    @classmethod
    def from_string(cls, name):
        return ResourceType[name.upper()] if name and name.upper() in ResourceType.__members__ else ResourceType.INVALID

    @classmethod
    def from_value(cls, value):
        return ResourceType(value) if isinstance(value, int) and \
                                      value in ResourceType._value2member_map_ else ResourceType.INVALID
