"""
(C) 2020 Splunk Inc. All rights reserved.

Module containing enums used in data objects
"""

from enum import Enum

class TVEventType(Enum):
    """
    Enum class enumerating types of
    drone mode tv subscription updates
    """
    NONE = 0
    TV_CONFIG = 1
    TV_INTERACTION = 2
    MPC_BROADCAST = 3

class TVConfigModeType(Enum):
    """
    Enum class enumerating types of
    drone mode TVConfig modes
    (Mirrors whats in protobuf)
    """
    UNKNOWN_MODE = 0
    DASHBOARD = 1
    IMAGE = 2
    DASHBOARD_GROUP = 3

class IPadEventType(Enum):
    """
    Enum class enumerating types of
    drone mode iPad subscription updates
    """
    NONE = 0
    TV_LIST = 1

class TVInteractionType(Enum):
    """
    Enum class enumerating different
    types of tv interactions
    """
    NONE = 0
    GOTO = 1
    STOP = 2
    FORWARD = 3
    BACK = 4
    SPEED = 5

class InputTokenChoiceType(Enum):
    """
    Enum class enumerating different
    types of user input token choices
    """
    UNKNOWN_CHOICE = 0
    CHECKBOX = 1
    MULTISELECT = 2
    RADIO = 3
    DROPDOWN = 4
    TEXTBOX = 5
    TIMEPICKER = 6

def is_valid_enum(cls, enum):
    """
    Function that determines whether or not the passed in value is
    valid for the provided enum
    """
    return enum in cls.__members__.values() or enum in cls._value2member_map_
