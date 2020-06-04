"""
(C) 2019 Splunk Inc. All rights reserved.

Data models for inputs for form dashboards
"""

import os
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
from abc import ABCMeta, abstractmethod
from spacebridgeapp.data.base import SpacebridgeAppBase
from splapp_protocol import form_inputs_pb2


class Timepicker(SpacebridgeAppBase):
    def __init__(self, label=None, default_earliest=None, default_latest=None):
        self.label = label
        self.default_earliest = default_earliest
        self.default_latest = default_latest

    def __eq__(self, obj):
        """Equality comparator
        """
        if isinstance(obj, self.__class__):
            return obj.label == self.label and \
                   obj.default_earliest == self.default_earliest and \
                   obj.default_earliest == self.default_earliest
        else:
            return False

    def set_protobuf(self, proto):
        """Takes a proto of type Timepicker and populates
         the fields with the corresponding class values

        Arguments:
            proto {Timepicker}
        """

        if self.label is not None:
            proto.label = self.label
        if self.default_earliest is not None:
            proto.defaultEarliest = self.default_earliest
        if self.default_latest is not None:
            proto.defaultLatest = self.default_latest

    def to_protobuf(self):
        """returns protobuf representation of this object

        Returns:

        """

        proto = form_inputs_pb2.Timepicker()
        self.set_protobuf(proto)
        return proto


class ChoiceValue(SpacebridgeAppBase):
    def __init__(self, choice, value):
        self.choice = choice
        self.value = value

    def __eq__(self, obj):
        """Equality comparator
        """
        if isinstance(obj, self.__class__):
            return obj.choice == self.choice and \
                   obj.value == self.value
        else:
            return False

    def set_protobuf(self, proto):
        """Takes a proto of type Timepicker and populates
         the fields with the corresponding class values

        Arguments:
            proto {Timepicker}
        """
        if self.choice:
            proto.choice = self.choice

        if self.value:
            proto.value = self.value

    def to_protobuf(self):
        """returns protobuf representation of this object

        Returns:

        """

        proto = form_inputs_pb2.ChoiceValue()
        self.set_protobuf(proto)
        return proto


class FormListInput(SpacebridgeAppBase):
    __metaclass__ = ABCMeta

    def __init__(self, label=None,
                 default_value=None,
                 initial_value=None,
                 choice_value_map=None,
                 token_prefix=None,
                 token_suffix=None,
                 token_value_prefix=None,
                 token_value_suffix=None,
                 choice_value_list=None,
                 delimiter=None,
                 dynamic_options=None):
        self.label = label
        self.default_value = default_value
        self.initial_value = initial_value
        self.choice_value_map = choice_value_map
        self.token_prefix = token_prefix
        self.token_suffix = token_suffix
        self.token_value_prefix = token_value_prefix
        self.token_value_suffix = token_value_suffix
        self.delimiter = delimiter
        self.choice_value_list = choice_value_list
        self.dynamic_options = dynamic_options

    def __eq__(self, obj):
        """Equality comparator
        """
        if isinstance(obj, self.__class__):
            return obj.label == self.label and \
                   obj.default_value == self.default_value and \
                   obj.initial_value == self.initial_value and \
                   obj.choice_value_map == self.choice_value_map and \
                   obj.token_prefix == self.token_prefix and \
                   obj.token_suffix == self.token_suffix and \
                   obj.token_value_prefix == self.token_value_prefix and \
                   obj.token_value_suffix == self.token_value_suffix and \
                   obj.delimiter == self.delimiter and \
                   obj.choice_value_list == self.choice_value_list and \
                   obj.dynamic_options == self.dynamic_options
        else:
            return False

    def set_protobuf(self, proto):
        """Takes a proto of type Timepicker and populates
         the fields with the corresponding class values

        Arguments:
            proto {Timepicker}
        """

        if self.label is not None:
            proto.label = self.label

        if self.default_value is not None:
            proto.defaultValue = self.default_value

        if self.initial_value is not None:
            proto.initialValue = self.initial_value

        if self.token_prefix is not None:
            proto.tokenPrefix = self.token_prefix

        if self.token_suffix is not None:
            proto.tokenSuffix = self.token_suffix

        if self.token_value_prefix is not None:
            proto.tokenValuePrefix = self.token_value_prefix

        if self.token_value_suffix is not None:
            proto.tokenValueSuffix = self.token_value_suffix

        if self.delimiter is not None:
            proto.delimiter = self.delimiter

        if self.choice_value_map is not None:
            for choice in self.choice_value_map.keys():
                value = self.choice_value_map[choice] if self.choice_value_map[choice] else ""
                if choice is not None:
                    proto.choiceValueMap[choice] = value
                else:
                    proto.choiceValueMap[""] = value

        if self.choice_value_list:
            choice_value_protos = [choice_value.to_protobuf() for choice_value in self.choice_value_list]
            proto.choiceValueList.extend(choice_value_protos)

        if self.dynamic_options:
            self.dynamic_options.set_protobuf(proto.dynamicOptions)

    def to_protobuf(self):
        """returns protobuf representation of this object

        Returns:

        """

        proto = self.get_empty_proto()
        self.set_protobuf(proto)
        return proto

    @abstractmethod
    def get_empty_proto(self):
        pass


class Dropdown(FormListInput):
    def get_empty_proto(self):
        return form_inputs_pb2.Dropdown()


class Radio(FormListInput):
    def get_empty_proto(self):
        return form_inputs_pb2.Radio()


class Checkbox(FormListInput):
    def get_empty_proto(self):
        return form_inputs_pb2.Checkbox()


class Multiselect(FormListInput):
    def get_empty_proto(self):
        return form_inputs_pb2.Multiselect()


class Textbox(FormListInput):
    def get_empty_proto(self):
        return form_inputs_pb2.Textbox()


class DynamicOptions(SpacebridgeAppBase):
    """
    Data object to represent Dynamic search options for form inputs (as opposed to static)
    """

    def __init__(self, field_for_value, field_for_label, query_id, search):
        self.field_for_value = field_for_value
        self.field_for_label = field_for_label
        self.query_id = query_id

        # don't need to persist search to proto
        self.search = search

    def to_protobuf(self):
        proto = form_inputs_pb2.DynamicOptions()
        self.set_protobuf(proto)
        return proto

    def set_protobuf(self, proto):
        proto.fieldForValue = self.field_for_value
        proto.fieldForLabel = self.field_for_label
        proto.queryId = self.query_id

