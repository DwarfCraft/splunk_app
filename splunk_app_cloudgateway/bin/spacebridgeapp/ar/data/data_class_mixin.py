import jsonpickle


class DataClassMixin(object):
    """A convenience for implementing common functionality on data classes."""

    def __eq__(self, other):
        return type(self) == type(other) and all(
            getattr(self, attr) == getattr(other, attr) for attr in vars(self).keys())

    def __ne__(self, other):
        return not self == other

    def to_json(self):
        # Don't write py/object field
        return jsonpickle.encode(self, unpicklable=False)
