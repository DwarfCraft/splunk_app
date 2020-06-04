"""
(C) 2020 Splunk Inc. All rights reserved.

Module for representation of data objects for event_handler
"""

import json
import os

os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

from splapp_protocol import event_handler_pb2, common_pb2
from spacebridgeapp.data.base import SpacebridgeAppBase
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME, VALUE, LABEL, MATCH
from spacebridgeapp.logging import setup_logging

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_event_handler.log", "event_handler")


class Change(SpacebridgeAppBase):
    """
    Container for data for change element. A change element contains set, unset, eval, link and conditions
    """

    def __init__(self, link=None, sets=None, evals=None, unsets=None, conditions=None):
        self.link = link
        self.sets = sets or []
        self.evals = evals or []
        self.unsets = unsets or []
        self.conditions = conditions or []

    def set_protobuf(self, proto):
        if self.link:
            self.link.set_protobuf(proto.link)

        if self.sets:
            set_protos = [set_obj.to_protobuf() for set_obj in self.sets]
            proto.sets.extend(set_protos)

        if self.evals:
            eval_protos = [eval_obj.to_protobuf() for eval_obj in self.evals]
            proto.evals.extend(eval_protos)

        if self.unsets:
            unset_protos = [unset_obj.to_protobuf() for unset_obj in self.unsets]
            proto.unsets.extend(unset_protos)

        if self.conditions:
            condition_protos = [condition_obj.to_protobuf() for condition_obj in self.conditions]
            proto.conditions.extend(condition_protos)

    def to_protobuf(self):
        proto = event_handler_pb2.Change()
        self.set_protobuf(proto)
        return proto

class FormCondition(SpacebridgeAppBase):
    """
    Container for data for condition element in form inputs. A condition element contains set, unset, eval, link
    """

    def __init__(self, matchAttribute, link=None, sets=None, evals=None, unsets=None):

        # Note: matchAttribute is an object that contains either value, label or match attributes
        self.matchAttribute = matchAttribute
        self.link = link
        self.sets = sets or []
        self.evals = evals or []
        self.unsets = unsets or []

    def set_protobuf(self, proto):
        if VALUE in self.matchAttribute and self.matchAttribute[VALUE] is not None:
            proto.value = self.matchAttribute[VALUE]
        elif LABEL in self.matchAttribute and self.matchAttribute[LABEL] is not None:
            proto.label = self.matchAttribute[LABEL]
        elif MATCH in self.matchAttribute and self.matchAttribute[MATCH] is not None:
            proto.match = self.matchAttribute[MATCH]

        if self.link:
            self.link.set_protobuf(proto.link)

        if self.sets:
            set_protos = [set_obj.to_protobuf() for set_obj in self.sets]
            proto.sets.extend(set_protos)

        if self.evals:
            eval_protos = [eval_obj.to_protobuf() for eval_obj in self.evals]
            proto.evals.extend(eval_protos)

        if self.unsets:
            unset_protos = [unset_obj.to_protobuf() for unset_obj in self.unsets]
            proto.unsets.extend(unset_protos)

    def to_protobuf(self):
        proto = event_handler_pb2.FormCondition()
        self.set_protobuf(proto)
        return proto

class Link(SpacebridgeAppBase):
    """
    A Link object used to specify links
    """
    def __init__(self, target='', url='', dashboard_id=None, input_map=None):
        self.target = target
        self.url = url
        self.dashboard_id = dashboard_id
        self.input_map = input_map if input_map else {}

    def set_protobuf(self, proto):
        proto.target = self.target
        proto.url = self.url
        proto.dashboardId = self.dashboard_id

        for key in self.input_map.keys():
            proto.inputMap[key] = self.input_map[key]

    def to_protobuf(self):
        proto = event_handler_pb2.Link()
        self.set_protobuf(proto)
        return proto

class Set(SpacebridgeAppBase):
    """
    A Set object used to specify set tokens
    """

    def __init__(self, token='', value=''):
        self.token = token
        self.value = value

    def set_protobuf(self, proto):
        proto.token = self.token
        proto.value = self.value

    def to_protobuf(self):
        proto = event_handler_pb2.Set()
        self.set_protobuf(proto)
        return proto

class Eval(SpacebridgeAppBase):
    """
    An Eval object used to specify eval functions
    """

    def __init__(self, token='', value=''):
        self.token = token
        self.value = value

    def set_protobuf(self, proto):
        proto.token = self.token
        proto.value = self.value

    def to_protobuf(self):
        proto = event_handler_pb2.Eval()
        self.set_protobuf(proto)
        return proto

class Unset(SpacebridgeAppBase):
    """
    An Unset object used to specify unset tokens
    """

    def __init__(self, token=''):
        self.token = token

    def set_protobuf(self, proto):
        proto.token = self.token

    def to_protobuf(self):
        proto = event_handler_pb2.Unset()
        self.set_protobuf(proto)
        return proto

class DrillDown(SpacebridgeAppBase):
    """
    A DrillDown object used to specify drilldown functions
    """
    def __init__(self, link=None, list_set=None, list_eval=None, list_unset=None, conditions=None):
        self.link = link
        self.list_set = list_set or []
        self.list_eval = list_eval or []
        self.list_unset = list_unset or []
        self.conditions = conditions or []

    def set_protobuf(self, proto):
        if self.link:
            self.link.set_protobuf(proto.link)

        if self.list_set:
            set_protos = [set_obj.to_protobuf() for set_obj in self.list_set]
            proto.sets.extend(set_protos)

        if self.list_eval:
            eval_protos = [eval_item.to_protobuf() for eval_item in self.list_eval]
            proto.evals.extend(eval_protos)

        if self.list_unset:
            unset_protos = [unset.to_protobuf() for unset in self.list_unset]
            proto.unsets.extend(unset_protos)

        if self.conditions:
            condition_protos = [condition_obj.to_protobuf() for condition_obj in self.conditions]
            proto.conditions.extend(condition_protos)

    def to_protobuf(self):
        proto = event_handler_pb2.DrillDown()
        self.set_protobuf(proto)
        return proto


class DrillDownCondition(SpacebridgeAppBase):
    """
    Container for data for condition element in drilldowns. A condition element contains set, unset, eval, link
    """

    def __init__(self, field, link=None, sets=None, evals=None, unsets=None):
        self.field = field
        self.link = link
        self.sets = sets or []
        self.evals = evals or []
        self.unsets = unsets or []

    def set_protobuf(self, proto):
        proto.field = self.field

        if self.link:
            self.link.set_protobuf(proto.link)

        if self.sets:
            set_protos = [set_obj.to_protobuf() for set_obj in self.sets]
            proto.sets.extend(set_protos)

        if self.evals:
            eval_protos = [eval_obj.to_protobuf() for eval_obj in self.evals]
            proto.evals.extend(eval_protos)

        if self.unsets:
            unset_protos = [unset_obj.to_protobuf() for unset_obj in self.unsets]
            proto.unsets.extend(unset_protos)

    def to_protobuf(self):
        proto = event_handler_pb2.DrillDownCondition()
        self.set_protobuf(proto)
        return proto

