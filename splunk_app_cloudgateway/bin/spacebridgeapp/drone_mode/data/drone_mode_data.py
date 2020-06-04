"""
(C) 2020 Splunk Inc. All rights reserved.

Module for representation of data objects for drone_mode
"""
import json
import base64
from google.protobuf.json_format import MessageToJson, ParseDict
from splapp_protocol import drone_mode_pb2
from spacebridgeapp.data.base import SpacebridgeAppBase
from spacebridgeapp.drone_mode.drone_mode_utils import has_grid, is_empty_grid
from spacebridgeapp.drone_mode.data.enums import TVInteractionType, TVConfigModeType, InputTokenChoiceType as user_choice_type, is_valid_enum
from spacebridgeapp.util import constants
from spacebridgeapp.util import py23
from spacebridgeapp.logging import setup_logging
LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_drone_mode_data.log",
                       "drone_mode_data")


class TVConfig(SpacebridgeAppBase):
    """Drone mode TV Config
    """

    def __init__(self,
                 device_id='',
                 device_name='',
                 mode=TVConfigModeType.UNKNOWN_MODE.value,
                 content='',
                 tv_grid=None,
                 timestamp='0',
                 captain_id='',
                 captain_url='',
                 input_tokens=None,
                 user_choices=None,
                 slideshow_duration=None,
                 _user='',
                 _key=''):

        self.device_id = device_id
        if _key and not device_id:
            raw_id = base64.urlsafe_b64decode(str(_key))
            self.device_id = py23.b64encode_to_str(raw_id)
        self.device_name = device_name
        self.mode = mode
        self.content = content
        self._user = _user
        self._key = _key

        if tv_grid is None:
            tv_grid = {}

        self.tv_grid = tv_grid
        # Important: note that proto's json representation of int64 fields is a string
        self.timestamp = timestamp
        self.captain_id = captain_id
        self.captain_url = captain_url

        if input_tokens is None:
            input_tokens = "{}"

        if user_choices is None:
            user_choices = "{}"
        self.user_choices = user_choices
        self.input_tokens = input_tokens
        self.slideshow_duration = slideshow_duration

    def set_input_tokens_in_proto(self, proto):
        """ Function to set input tokens to a given proto"""
        input_tokens = json.loads(self.input_tokens)
        for dashboard_id, token_map in input_tokens.items():

            input_token_map = drone_mode_pb2.InputTokenMap()
            for token_name, token_string in token_map[constants.INPUT_TOKENS].items():

                input_token_map.input_tokens[token_name] = token_string
            proto.input_tokens[dashboard_id].CopyFrom(input_token_map)

    def set_user_choices_in_proto(self, proto):
        """ Function to set user choices to a given proto"""
        user_choices = json.loads(self.user_choices)

        for dashboard_id, choice_map in user_choices.items():
            input_choice_map = drone_mode_pb2.InputChoiceMap()
            for token_name, user_choice in choice_map[constants.INPUT_CHOICES].items():
                token_choice = drone_mode_pb2.InputTokenChoice()
                ParseDict(user_choice, token_choice)
                input_choice_map.input_choices[token_name].CopyFrom(token_choice)
            proto.user_choices[dashboard_id].CopyFrom(input_choice_map)

    def set_protobuf(self, proto):
        """Takes a proto of type TVConfig and populates
         the fields with the corresponding class values

        Arguments:
            proto {TVConfig}
        """
        proto.device_id = self.device_id
        proto.device_name = self.device_name
        proto.mode = int(self.mode)
        proto.content = self.content

        if self.tv_grid and not is_empty_grid(self.tv_grid):
            proto.tv_grid.width = int(self.tv_grid.get('width', 0))
            proto.tv_grid.height = int(self.tv_grid.get('height', 0))
            proto.tv_grid.position = int(self.tv_grid.get('position', 0))
            proto.tv_grid.device_ids.extend(self.tv_grid.get('device_ids', []))

        proto.timestamp = int(self.timestamp)

        if self.captain_id:
            proto.captain_id = self.captain_id

        if self.captain_url:
            proto.captain_url = self.captain_url

        if self.input_tokens:
            self.set_input_tokens_in_proto(proto)

        if self.user_choices:
            self.set_user_choices_in_proto(proto)

        if self.slideshow_duration is not None:
            proto.slideshow_duration = self.slideshow_duration

    def from_protobuf(self, proto):
        """
        Takes a protobuf and sets fields on class

        Arguments:
            proto {TVConfig}
        """
        self.device_id = proto.device_id
        self.device_name = proto.device_name
        self.mode = proto.mode
        self.content = proto.content

        if proto.tv_grid:
            self.tv_grid = {'width': proto.tv_grid.width,
                            'height': proto.tv_grid.height,
                            'position': proto.tv_grid.position,
                            'device_ids': proto.tv_grid.device_ids
                           }

        self.timestamp = str(proto.timestamp)

        if proto.captain_id:
            self.captain_id = proto.captain_id

        if proto.captain_url:
            self.captain_url = proto.captain_url

        if proto.input_tokens or proto.user_choices:
            proto_dict = json.loads(MessageToJson(proto, including_default_value_fields=True, preserving_proto_field_name=True))

        if proto.input_tokens:
            self.input_tokens = json.dumps(proto_dict.get(constants.INPUT_TOKENS))

        if proto.user_choices:
            self.user_choices = json.dumps(proto_dict.get(constants.USER_CHOICES))

        if proto.slideshow_duration is not None:
            self.slideshow_duration = proto.slideshow_duration

    def to_protobuf(self):
        """returns protobuf representation of this object

        Returns:
            proto {TVConfig}
        """

        proto = drone_mode_pb2.TVConfig()
        self.set_protobuf(proto)
        return proto

    @staticmethod
    def required_kvstore_keys():
        """
        Required keys needed for json representation of tv config in kvstore
        """
        return {
            constants.DEVICE_NAME,
            constants.MODE,
            constants.CONTENT,
            constants.TV_GRID,
            constants.TIMESTAMP,
            constants.SLIDESHOW_DURATION,
            constants.INPUT_TOKENS,
            constants.CAPTAIN_ID,
            constants.CAPTAIN_URL
        }

class TVBookmark(SpacebridgeAppBase):
    """Drone mode TV Bookmark"""

    def __init__(self,
                 tv_config_map=None,
                 description='',
                 name='',
                 _user='',
                 _key=''):

        if tv_config_map is None:
            tv_config_map = {}

        self.tv_config_map = tv_config_map
        self.description = description
        self.name = name
        self._key = _key
        self._user = _user

    def set_protobuf(self, proto):
        """Takes a proto of type TVBookmark and populates
         the fields with the corresponding class values

        Arguments:
            proto {TVBookmark}
        """
        proto.description = self.description
        proto.name = self.name

        for device_id in self.tv_config_map:
            LOGGER.debug('In set protobuf: device_id=%s, tv_config=%s',
                         device_id,
                         self.tv_config_map[device_id])
            tv_config_proto = TVConfig(**self.tv_config_map[device_id]).to_protobuf()
            proto.tv_config_map[device_id].CopyFrom(tv_config_proto)

    def from_protobuf(self, proto):
        """
        Takes a protobuf and sets fields on class

        Arguments:
            proto {TVBookmark}
        """
        self.description = proto.description
        self.name = proto.name
        json_proto = MessageToJson(proto, including_default_value_fields=True, preserving_proto_field_name=True, use_integers_for_enums=True)
        tv_config_map = json.loads(json_proto).get(constants.TV_CONFIG_MAP, {})
        # input tokens needs to be a json blob
        for key, value in tv_config_map.items():
            value[constants.INPUT_TOKENS] = json.dumps(value.get(constants.INPUT_TOKENS, "{}"))
            value[constants.USER_CHOICES] = json.dumps(value.get(constants.USER_CHOICES, "{}"))
        self.tv_config_map = tv_config_map

    def to_protobuf(self):
        """returns protobuf representation of this object

        Returns:
            proto {TVBookmark}
        """

        proto = drone_mode_pb2.TVBookmark()
        self.set_protobuf(proto)
        return proto

class StartMPCBroadcast(SpacebridgeAppBase):
    """Drone Mode TV Broadcast"""
    def __init__(self, device_id=''):
        self.device_id = device_id

    def set_protobuf(self, proto):
        """
        Takes a proto of the type StartMPCBroadcast and
        sets the device_id field

        Arguments:
            proto {StartMPCBroadcast}
        """
        proto.device_id = self.device_id

    def from_protobuf(self, proto):
        """
        Takes a protobuf and sets the class
        device_id attribute
        """
        self.device_id = proto.device_id

    def to_protobuf(self):
        """Returns protobuf representation of this object"""
        proto = drone_mode_pb2.StartMPCBroadcast()
        self.set_protobuf(proto)
        return proto

class TVInteraction(SpacebridgeAppBase):
    """TV Interaction"""
    def __init__(self, device_id, interaction_type=TVInteractionType.NONE, speed=None):

        if not is_valid_enum(TVInteractionType, interaction_type):
            raise ValueError('Invalid Drone Mode TV Interaction Type={}'.format(interaction_type))
        self.device_id = device_id
        self.interaction_type = interaction_type
        self.speed = speed

    def set_protobuf(self, proto):
        """Takes a proto of type TVInteraction and populates
        the fields with the corresponding class values

        Arguments:
            proto {TVInteraction}
        """
        proto.device_id = self.device_id
        if self.interaction_type == TVInteractionType.GOTO:
            proto.slideshow_go_to.SetInParent()
        elif self.interaction_type == TVInteractionType.STOP:
            proto.slideshow_stop.SetInParent()
        elif self.interaction_type == TVInteractionType.FORWARD:
            proto.slideshow_forward.SetInParent()
        elif self.interaction_type == TVInteractionType.BACK:
            proto.slideshow_back.SetInParent()
        elif self.interaction_type == TVInteractionType.SPEED:
            proto.slideshow_speed.speed = self.speed
        else:
            raise ValueError('Invalid interaction type')

    def to_protobuf(self):
        """Returns protobuf representation of this object

        Returns:
            proto {TVInteraction}
        """
        proto = drone_mode_pb2.TVInteraction()
        self.set_protobuf(proto)
        return proto

class TVData(SpacebridgeAppBase):
    """TVData"""
    def __init__(self, tv_config, display_name, device_id, is_active):
        self.tv_config = tv_config
        self.display_name = display_name
        self.device_id = device_id
        self.is_active = is_active

    def set_protobuf(self, proto):
        """Takes a proto of type TVData and
        populates the fields with the corresponding class values

        Arguments:
            proto {TVData}
        """
        proto.tv_config.CopyFrom(TVConfig(**self.tv_config).to_protobuf())
        proto.display_name = self.display_name
        proto.device_id = self.device_id
        proto.is_active = self.is_active

    def to_protobuf(self):
        """ Returns protobuf representation of this object

        Returns:
            proto {TVData}
        """
        proto = drone_mode_pb2.TVData()
        self.set_protobuf(proto)
        return proto

class TVList(SpacebridgeAppBase):
    """TV List"""
    def __init__(self, tv_data_list):
        self.tv_data_list = tv_data_list

    def set_protobuf(self, proto):
        """Takes a proto of the type TVList and
        populates the fields withthe corresponding class values

        Arguments:
            proto {TVList}
        """
        tv_list = [TVData(**tv_data).to_protobuf() for tv_data in self.tv_data_list]
        proto.tv_data.extend(tv_list)

    def to_protobuf(self):
        """ Returns protobuf representation of this object

        Returns:
            proto {TVList}
        """
        proto = drone_mode_pb2.TVList()
        self.set_protobuf(proto)
        return proto
