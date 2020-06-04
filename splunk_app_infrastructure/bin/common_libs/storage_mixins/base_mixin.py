from abc import abstractmethod, ABCMeta
from six import with_metaclass


class AbstractBaseStorageMixin(with_metaclass(ABCMeta)):
    '''
    AbstractBaseStorageMixin defines an interface where subclass should implement in order to be
    considered a storage mixin. And the actual implementaion depends on the storage type that the
    subclass represents. To use a storage mixin class, simply append it as a superclass and implement
    its required methods (`app_name` and `storage_name`) to satisfy its interface. Then the subclass
    of the specific storage mixin class will be able to call all the `storage_<operation>` methods directly.
    e.g.

    >>> # KVStoreMixin implements AbstractBaseStorageMixin
    >>> from storage_mixin import KVStoreMixin
    >>>
    >>> class Group(KVStoreMixin):
    >>>     @classmethod
    >>>     def app_name(cls):
    >>>         return 'sample_app'
    >>>
    >>>     @classmethod
    >>>     def storage_name(cls):
    >>>         return 'group_store'
    >>>
    >>>     @classmethod
    >>>     def get(cls, key):
    >>>         # no need to implement the actual communication with kvstore or create and manage a manager instance.
    >>>         group_data = self.storage_get(key)
    >>>         ... # do more stuff with the group data
    '''

    @classmethod
    @abstractmethod
    def app_name(cls):
        '''
        This method MUST be overriden by subclass - App name is the name of the app
        under whose namespace the storage is defined.
        '''
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def storage_name(cls):
        '''
        This method MUST be overriden by subclass - Storage name is the name of the storage.
        It means different things for different kinds of storage, for example, it's the collecion
        name for KVStore, the conf file name for conf based storage.
        '''
        raise NotImplementedError()

    @classmethod
    def storage_get(cls, key):
        '''
        This method should be overriden by subclass - this method performs a get operation based
        on id of the object to be retrieived.
        '''
        raise NotImplementedError()

    @classmethod
    def storage_load(cls, **kwargs):
        '''
        This method should be overriden by subclass - this method performs a bulk load operation
        based on certain input parameters like count, offset, etc. The exact parameter set should
        be defined by the subclass based on storage type.
        '''
        raise NotImplementedError()

    @classmethod
    def storage_batch_save(cls, objects):
        '''
        This method should be overriden by subclass - this method performs a batch save operation and
        saves the input objects into its storage location.
        '''
        raise NotImplementedError()

    @classmethod
    def storage_save(cls, key, data):
        '''
        This method should be overriden by subclass - this method performs an individual save operation
        on the caller, and saves the caller's current state into its storage location.
        '''
        raise NotImplementedError()

    def storage_delete(self):
        '''
        This method should be overriden by subclass - this method performs a delete operation on the caller
        and deletes itself from its storage location.
        '''
        raise NotImplementedError()
