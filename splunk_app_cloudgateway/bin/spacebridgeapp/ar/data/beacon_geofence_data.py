"""
(C) 2019 Splunk Inc. All rights reserved.

Module for representation of data objects for beacons and geofences
"""
import os

from spacebridgeapp.ar.data.data_class_mixin import DataClassMixin
from spacebridgeapp.util.constants import GEOFENCE, BEACON, GEOFENCE_DEFINITION, BEACON_DEFINITION
from splapp_protocol import common_pb2
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'


class BeaconRegion(DataClassMixin):
    """ A beacon region consists of a uuid, and a title which may accompany that uuid
    """
    def __init__(self,
                 uuid,
                 title=""):
        self.uuid = uuid
        self.title = title

    def set_protobuf(self, proto):
        """Build class from protobuf

        :param proto: {BeaconRegion} protobuf object
        :return: BeaconRegion python object
        """
        proto.uuid = self.uuid
        proto.title = self.title

    def to_protobuf(self):
        """Build protobuf from class

        :param proto: {BeaconRegion} protobuf object
        :return: BeaconRegion python object
        """
        proto = common_pb2.BeaconRegion()
        self.set_protobuf(proto)
        return proto

    @classmethod
    def from_json(cls, json):
        """ Build class from json

        :param json: json containing uuid and title keys
        :return: BeaconRegion instance
        """
        return cls(json['uuid'], json['title'])


class BeaconDefinition(DataClassMixin):
    """ A Beacon Definition consists of a uuid, and two ints
    (a major and a minor).
    """
    def __init__(self, uuid, major, minor):
        self.uuid = uuid
        self.major = major
        self.minor = minor

    def set_protobuf(self, proto):
        """fills in protobuf from self

        :param proto: {BeaconDefinition} protobuf object
        """
        proto.key.uuid = self.uuid
        proto.key.major = self.major
        proto.key.minor = self.minor

    def to_protobuf(self):
        """Build protobuf from internal state

        :return: BeaconDefinition protobuf
        """
        proto = common_pb2.NearbyEntity.BeaconDefinition()
        self.set_protobuf(proto)
        return proto

    def kvstore_params(self):
        """Return the kvstore params to specify this beacon definition
        """
        return self.__dict__

    @classmethod
    def from_protobuf(cls, proto):
        """Build class from protobuf
        """
        return cls(proto.key.uuid, proto.key.major, proto.key.minor)

    @classmethod
    def from_json(cls, json):
        """ Build class from json

        :param json: json containing uuid, major and minor fields
        :return: BeaconDefinition instance
        """
        return cls(json['key']['uuid'],
                   json['key']['major'],
                   json['key']['minor'])


class GeofenceDefinition(DataClassMixin):
    """ A Geofence Definition consists of a key and a geofenceDefinition """

    def __init__(self, key, latitude, longitude, radius):
        self.key = key
        self.latitude = latitude
        self.longitude = longitude
        self.radius = radius

    def set_protobuf(self, proto):
        """fills in protobuf from self

        :param proto: {GeofenceDefinition} protobuf object
        """

        proto.key = self.key
        proto.circularGeofence.center.latitude = self.latitude
        proto.circularGeofence.center.longitude = self.longitude
        proto.circularGeofence.radius = self.radius

    def to_protobuf(self):
        """Build protobuf from internal state

        :return: GeofenceDefinition protobuf
        """

        proto = common_pb2.NearbyEntity.GeofenceDefinition()
        self.set_protobuf(proto)
        return proto

    def kvstore_params(self):
        """Return the kvstore params to specify this beacon definition
        """
        return self.__dict__

    @classmethod
    def from_protobuf(cls, proto):
        """Build class from protobuf
        """

        return cls(proto.key,
                   proto.circularGeofence.center.latitude,
                   proto.circularGeofence.center.longitude,
                   proto.circularGeofence.radius)

    @classmethod
    def from_json(cls, json):
        """ Build class from json

        :param json: json containing uuid, major and minor fields
        :return: BeaconDefinition instance
        """
        return cls(json['key'],
                   json['circularGeofence']['center']['latitude'],
                   json['circularGeofence']['center']['longitude'],
                   json['circularGeofence']['radius'])


class NearbyEntity(DataClassMixin):
    """ A NearbyEntity Definition consists of a title and a nearbyEntity Type """

    def __init__(self, title, entity_type, **kwargs):
        if not entity_type:
            raise ValueError('You must provide an entity type')

        if entity_type == BEACON:
            self.entity_type = BEACON
            self.uuid = kwargs.get('uuid')
            self.major = kwargs.get('major')
            self.minor = kwargs.get('minor')

        elif entity_type == GEOFENCE:
            self.entity_type = GEOFENCE
            self.key = kwargs.get('key')
            self.latitude = kwargs.get('latitude')
            self.longitude = kwargs.get('longitude')
            self.radius = kwargs.get('radius')

        else:
            raise ValueError('You have provided an invalid entity type')

        self.title = title

    def set_protobuf(self, proto):
        """fills in protobuf from self

        :param proto: {GeofenceDefinition} protobuf object
        """

        proto.title = self.title
        if self.entity_type == BEACON:
            beacon_definition = BeaconDefinition(self.uuid, self.major, self.minor)
            proto.beaconDefinition.CopyFrom(beacon_definition.to_protobuf())

        elif self.entity_type == GEOFENCE:
            geofence_definition = GeofenceDefinition(self.key,
                                                     self.latitude,
                                                     self.longitude,
                                                     self.radius)
            proto.geofenceDefinition.CopyFrom(geofence_definition.to_protobuf())

    def to_protobuf(self):
        """Build protobuf from internal state

        :return: NearbyEntity protobuf
        """

        proto = common_pb2.NearbyEntity()
        self.set_protobuf(proto)
        return proto

    def kvstore_params(self):
        """Return the kvstore params to specify this beacon definition
        """
        return self.__dict__

    @classmethod
    def from_protobuf(cls, proto):
        """Build class from protobuf
        """
        if proto.HasField(GEOFENCE_DEFINITION):
            return cls(proto.title,
                       GEOFENCE,
                       key=proto.geofenceDefinition.key,
                       latitude=proto.geofenceDefinition.circularGeofence.center.latitude,
                       longitude=proto.geofenceDefinition.circularGeofence.center.longitude,
                       radius=proto.geofenceDefinition.circularGeofence.radius)

        return cls(proto.title,
                   BEACON,
                   uuid=proto.beaconDefinition.key.uuid,
                   major=proto.beaconDefinition.key.major,
                   minor=proto.beaconDefinition.key.minor)

    @classmethod
    def from_json(cls, json):
        """ Build class from json

        :param json: json containing uuid, major and minor fields
        :return: BeaconDefinition instance
        """
        if GEOFENCE_DEFINITION in json:
            return cls(json['title'],
                       GEOFENCE,
                       key=json[GEOFENCE_DEFINITION]['key'],
                       latitude=json[GEOFENCE_DEFINITION]['circularGeofence']['center']['latitude'],
                       longitude=json[GEOFENCE_DEFINITION]['circularGeofence']['center']['longitude'],
                       radius=json[GEOFENCE_DEFINITION]['circularGeofence']['radius'])

        return cls(json['title'],
                   BEACON,
                   uuid=json[BEACON_DEFINITION]['key']['uuid'],
                   major=json[BEACON_DEFINITION]['key']['major'],
                   minor=json[BEACON_DEFINITION]['key']['minor'])


class BeaconDashboardPair(DataClassMixin):
    """ A Beacon Dashboard Pair consists of a BeaconDefinition and a DashboardDescription
    """
    def __init__(self, beacon, dashboard):
        self.beacon = beacon
        self.dashboard = dashboard

    def set_protobuf(self, proto):
        """fills in protobuf from self

        :param proto: {BeaconDashboardPair} protobuf object
        """
        self.beacon.set_protobuf(proto.beacon)
        self.dashboard.set_protobuf(proto.dashboard)

    def to_protobuf(self):
        """Build class from protobuf

        :return: BeaconDashboardPair protobuf
        """
        proto = common_pb2.BeaconDashboardPair()
        self.set_protobuf(proto)
        return proto
