"""
(C) 2019 Splunk Inc. All rights reserved.

Module for any base classes that we want other data classes
to inherit from
"""

from abc import ABCMeta
import jsonpickle


class SpacebridgeAppBase(object):
    """Base level abstract class for data objects which provides common utilities
    such as returning a json representation of the object.
    """

    __metaclass__ = ABCMeta

    def __repr__(self):
        return jsonpickle.encode(self)

    def __eq__(self, obj):
        if isinstance(obj, self.__class__):
            return all(getattr(obj, attr) == getattr(self, attr) for attr in vars(self).keys())
        return False

    def __ne__(self, obj):
        """Overrides the default implementation (unnecessary in Python 3)"""
        return not self.__eq__(obj)

    def to_json(self):
        """
        Object helper method to write object to json without py/object metadata
        :return:
        """
        return jsonpickle.encode(self, unpicklable=False)  # Don't write py/object field
