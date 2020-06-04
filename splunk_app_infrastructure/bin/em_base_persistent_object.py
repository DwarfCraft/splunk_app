from abc import abstractmethod

import em_path_inject  # noqa
from storage_mixins import AbstractBaseStorageMixin
import em_constants

from splunk import getDefault
from splunklib.client import Service
from rest_handler.session import session, authtoken_required


class EMBasePersistentObject(AbstractBaseStorageMixin):
    '''
    EMBasePersistentObject is the superclass of all SAI knowledge objects that needs a persistent storage layer.
    It should be used with a storage mixin class (any subclass of the AbstractBaseStorageMixin) together
    based on storage type and this coupling is enforced programmatically. The base class itself provides some
    rough implementation of reading and retrieving data from the storage layer, but is open to be customized/overriden
    by its subclass.

    Usage example:
    >>> class Group(EMBasePersistentObject, KVStoreMixin):
    >>>     @classmethod
    >>>     def _from_raw(cls, data):
    >>>         ...
    >>>
    >>>     def _raw(self):
    >>>         ...
    >>>
    >>>     @classmethod(cls)
    >>>     def storage_name(cls):
    >>>         return 'group_store'
    >>>
    >>> group = Group.get('example-group-key')
    <object of type 'Group'>
    >>> group.title = 'new title'
    >>> group.save()
    '''

    @classmethod
    @abstractmethod
    def _from_raw(cls, data):
        '''
        This method MUST be overriden by subclass - _from_raw is used to transform raw data (in json or other format)
        to convert returned data from storage layer into an object of the class itself.

        :param data: json data
        :return an object of type 'cls'
        '''
        raise NotImplementedError()

    @abstractmethod
    def _raw(self):
        '''
        This method MUST be overriden by sublcass - the _raw method is called when performing a save operation to the
        storage layer. It should transform the `self` object into raw format that's stored in the storage layer.

        NOTE: This should not be confused with converting data to the raw format for REST API response
        unless if the API is using the same format as the storage layer
        '''
        raise NotImplementedError()

    @classmethod
    def app_name(cls):
        '''
        This overrides the `app_name` method in `AbstractBaseStorageMixin`
        '''
        return em_constants.APP_NAME

    @property
    @authtoken_required
    def service(self):
        if getattr(self, '_service', None):
            return self._service
        self._service = Service(
            port=getDefault('port'),
            token=session['authtoken'],
            app=em_constants.APP_NAME,
            owner='nobody'
        )
        return self._service

    @classmethod
    def get(cls, key):
        data = cls.storage_get(key)
        if data is None:
            return None
        return cls._from_raw(data)

    @classmethod
    def load(cls, **params):
        data_list = cls.storage_load(**params)
        objects = [cls._from_raw(d) for d in data_list]
        return objects

    @classmethod
    def create(cls, data):
        data = cls.storage_create(data)
        return cls._from_raw(data)

    def save(self):
        data = self._raw()
        self.storage_save(self.key, data)

    def delete(self):
        raise NotImplementedError()
