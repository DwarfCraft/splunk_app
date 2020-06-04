import em_path_inject  # noqa
import time

from splunklib.client import Service
from storage_mixins import KVStoreMixin
from rest_handler.session import session
from logging_utils import log
import em_constants
import em_common
from em_base_persistent_object import EMBasePersistentObject
from em_model_entity_class import EntityClass
from em_correlation_filters import create_entity_log_filter

logger = log.getLogger()


class InvalidEntityException(Exception):
    pass


class EntityInternalException(Exception):
    pass


class EmEntity(EMBasePersistentObject, KVStoreMixin):
    '''
    Entity model - Each entity represents an object (e.g. a linux machine, a EC2 instance) that is
    monitoried by SAI. Entity is discovered from data and its dimensions comes from the data
    from which it is discovered.

    Attributes:
        - key: primary key of an entity in its persistent storage (e.g. kvstore)
        - title: title of the entity
        - entity_class: entity class that this entity belongs to (e.g. aws_cloudwatch_ec2)
        - mod_time: when is this entity last updated
        - expiry_time: when is the status of this entity considered expired and no longer valid
        - identifier_dimension_names: list of dimension names whose values uniquely identifies
                                      an entity within an entity class
        - dimensions: A dictionary of dimension name-value kv pairs
    '''

    # STATUS_UPDATE_LAG is the maximum time (in seconds) it takes to update an entity's status
    # An entity's status should be considered invalid if the query_time <= expiry_time + STATUS_UPDATE_LAG
    STATUS_UPDATE_LAG = 60

    ACTIVE = 'active'
    INACTIVE = 'inactive'

    _entity_classes_cache = None

    def __init__(
        self,
        key,
        title,
        entity_class,
        mod_time,
        expiry_time,
        identifier_dimension_names,
        dimensions
    ):
        self.key = key
        self.title = title
        self.entity_class = entity_class
        self.mod_time = mod_time
        self.expiry_time = expiry_time
        self.identifier_dimension_names = identifier_dimension_names
        if isinstance(self.identifier_dimension_names, list):
            self.identifier_dimension_names.sort()
        self.dimensions = dimensions
        self._validate()

    def _validate(self):
        errs = []
        if not isinstance(self.mod_time, int):
            errs.append('mod_time should be "int" instead of %s' % type(self.mod_time))
        if not isinstance(self.expiry_time, int):
            errs.append('expiry_time should be "int" instead of %s' % type(self.expiry_time))
        if not isinstance(self.identifier_dimension_names, list):
            errs.append(
                'identifier_dimension_names should be "list" instead of %s' % type(self.identifier_dimension_names)
            )
        if not isinstance(self.dimensions, dict):
            errs.append('dimensions should be "dict" instead of %s' % type(self.dimensions))
        if len(errs):
            err_msg = 'entity: %s - Error: %s' % (self.key, '. '.join(errs))
            raise InvalidEntityException(err_msg)

    @classmethod
    def storage_name(cls):
        '''
        This method implements `storage_name` of `AbstractBaseStorageMixin`
        '''
        return em_constants.STORE_ENTITY_CACHE

    @classmethod
    def _from_raw(cls, data):
        '''
        This method implements `_from_raw` of `EMBasePersistentObject`
        '''
        id_dims = data.get('identifier_dimensions')
        if not id_dims:
            raise InvalidEntityException('identifier_dimensions is missing')
        id_dims_list = [id_dims] if not isinstance(id_dims, list) else id_dims
        dimensions = EmEntity.convert_dimensions_list_to_dict(data.get('dimensions_kv', []))
        return EmEntity(
            key=data['_key'],
            title=data['title'],
            entity_class=data['entity_class'],
            mod_time=int(data['mod_time']),
            expiry_time=int(data['expiry_time']),
            identifier_dimension_names=id_dims_list,
            dimensions=dimensions
        )

    def _raw(self):
        '''
        This method implements `_raw` of `EMBasePersistentObject`
        '''
        dimensions_kv = EmEntity.convert_dimensions_dict_to_list(self.dimensions)
        return {
            '_dimensions_kv_lookup': [val.lower() for val in dimensions_kv],
            '_key': self.key,
            '_user': 'nobody',
            'dimensions_kv': dimensions_kv,
            'entity_class': self.entity_class,
            'expiry_time': self.expiry_time,
            'identifier_dimensions': self.identifier_dimension_names,
            'mod_time': self.mod_time,
            'title': self.title,
        }

    @property
    def status(self):
        cur_time = time.time()
        if self.expiry_time + EmEntity.STATUS_UPDATE_LAG >= cur_time:
            return EmEntity.ACTIVE
        return EmEntity.INACTIVE

    @classmethod
    def load(cls, count, offset, sort_key, sort_dir, query=None):
        '''
        Load entities based on input parameters

        :param count: how many entities to load
        :type int
        :param offset: starting offset of entities to load
        :type int
        :param sort_key: key based on which the result is sorted (note: sorting is done before count and offset)
        :type str
        :param sort_dir: sort direction, can be either 'asc' or 'desc'
        :type str
        :param query: a filter query in {<key>: [<value>, <value>...]} format
        :type dict

        :return a list of EmEntity objects
        :rtype list
        '''
        sort_param = []
        if sort_key:
            if sort_key in em_constants.STATUS_KEYS:
                sort_key = 'expiry_time'
                sort_dir = 'asc' if sort_dir == 'desc' else 'desc'
            sort_param = [(sort_key, sort_dir)]
        kvstore_query = EmEntity.convert_filter_to_kvstore_query(query)
        return super(EmEntity, cls).load(
            limit=count,
            skip=offset,
            sort_keys_and_orders=sort_param,
            fields='',
            query=kvstore_query
        )

    @classmethod
    def bulk_delete(cls, delete_filter_dict=None, exclusion_list=None):
        '''
        Bulk delete entities specified by delete_filter_dict, if delete_filter_dict is None then delete all entities
        This method will also delete any associated alerts of the deleted entities

        :param delete_filter_dict: a entity filter dict that specifies the entities to delete. e.g. {'_key': ['a', 'b']}
        :param exclusion_list: a list of keys of entities that should *NOT* be deleted
        '''
        # build exclusion query
        exclusion_list = [] if exclusion_list is None else exclusion_list
        exclusion_query = None
        if len(exclusion_list):
            exclusion_filter = {'_key': exclusion_list}
            exclusion_query = em_common.negate_special_mongo_query(
                cls.convert_filter_to_kvstore_query(exclusion_filter)
            )

        # build delete query
        filter_delete_query = cls.convert_filter_to_kvstore_query(delete_filter_dict)
        if exclusion_query is None:
            delete_query = filter_delete_query
        else:
            if filter_delete_query is None:
                filter_delete_query = {}
            delete_query = {'$and': [filter_delete_query, exclusion_query]}

        # get key of entities to be deleted
        entities_to_delete = super(EmEntity, cls).load(
            limit=0, skip=0, sort_keys_and_orders=[], fields='', query=delete_query
        )
        entity_keys_to_delete = [entity.key for entity in entities_to_delete]

        if len(entity_keys_to_delete):
            # bulk delete entities
            cls.storage_bulk_delete(delete_query)
            # bulk delete all associated alert savedsearch
            svc = Service(token=session['authtoken'], app=em_constants.APP_NAME, owner='nobody')
            # delete alerts in batches to avoid 'Request-URI Too Long'
            batch_size = 4000  # found by trial and error
            batches = (entity_keys_to_delete[x:x + batch_size]
                       for x in range(0, len(entity_keys_to_delete), batch_size))
            for batch in batches:
                for alert_ss in svc.saved_searches.iter(
                    search=' OR '.join(
                        'alert.managedBy={}:{}'.format(em_constants.APP_NAME, eid) for eid in batch
                    )
                ):
                    logger.info('bulk delete cleanup - deleting alert %s' % alert_ss.name)
                    alert_ss.delete()

    def get_entity_class_info(self):
        '''
        Get info about the entity class of this entity
        '''
        # cache entity classes info at class level so we don't need to retrieve it every time
        if EmEntity._entity_classes_cache is None:
            entity_classes = EntityClass.load()
            EmEntity._entity_classes_cache = {ec.key: ec for ec in entity_classes}
        entity_class_info = EmEntity._entity_classes_cache[self.entity_class]
        return entity_class_info

    def get_correlation_filter(self):
        '''
        Get correlation filter of this entity that can be used to find data in events index
        that's related to the entity
        '''
        entity_class = self.get_entity_class_info()
        correlation_filter = create_entity_log_filter(self, [entity_class])
        return correlation_filter

    @classmethod
    def get_metadata(cls, filter_dict):
        '''
        Get metdata of entities filtered by query.
        '''
        kvstore_query = EmEntity.convert_filter_to_kvstore_query(filter_dict)
        entity_keys = cls.storage_load(0, 0, [], fields='_key', query=kvstore_query)
        return {
            'total_count': len(entity_keys)
        }

    @classmethod
    def get_dimension_summary(cls, filter_dict=None):
        '''
        Get dimension summary of all entities filtered by filter_dict
        '''
        entities = EmEntity.load(0, 0, '', 'asc', query=filter_dict)

        merged_dimensions = {}
        for entity in entities:
            for key, value in entity.dimensions.items():
                value = value if isinstance(value, list) else [value]
                merged_dimensions.setdefault(key, []).extend(value)
        # deduplicate merged dimensions value in the end
        for dim in merged_dimensions:
            merged_dimensions[dim] = list(set(merged_dimensions[dim]))
        return merged_dimensions

    @staticmethod
    def convert_dimensions_list_to_dict(dimensions_kv_list):
        '''
        Utility method that converts the dimensions data in the form of a list of kv-pairs to
        an identifier dimensions dict and an informational dimensions dict.

        :param dimensions_kv_list: list of dimensions kv pairs. e.g. ['host=a.usa.com', 'tag=prod']
        :return dimensions dict. e.g. {'host': ['a.usa.com'], 'tag': ['prod']}
        '''
        dims = {}
        for dim_kv in dimensions_kv_list:
            dim_name, dim_value = dim_kv.split('=', 1)
            dims.setdefault(dim_name, []).append(dim_value)
        return dims

    @staticmethod
    def convert_dimensions_dict_to_list(dimensions_kv_dict):
        '''
        Utility method that converts the dimensions data in the form of a dict of kv-pairs to
        a list.

        :param dimensions_kv_dict: dict of dimensions kv pairs. e.g. {'host': ['a.usa.com'], 'tag': ['prod']}
        :return dimensions list. e.g. ['host=a.usa.com', 'tag=prod']
        '''
        dims = []
        for k, v in dimensions_kv_dict.items():
            values = v if isinstance(v, list) else [v]
            for value in values:
                dims.append('='.join([k, value]))
        return dims

    @staticmethod
    def convert_filter_to_kvstore_query(filter_dict):
        '''
        Utillity method that converts a filter dict entity query into a kvstore (mongo) entity query.

        :param filter_dict - A filter dict query: {
            'dimensions.host': 'abc.com',
            'title': 'hello'
        }
        :return An equivalent kvstore (mongo) query
        '''
        if not filter_dict or filter_dict == {}:
            return None
        sub_queries = []
        for filter_name, filter_value in filter_dict.items():
            if filter_name.startswith('dimensions.'):
                dimension_name = filter_name[len('dimensions.'):]
                sub_query = EmEntity._build_dimension_filter_query(dimension_name, filter_value)
            elif filter_name.lower() in em_constants.STATUS_KEYS:
                sub_query = EmEntity._build_status_query(filter_value)
            else:
                sub_query = EmEntity._build_regular_filter_query(filter_name, filter_value)
            sub_queries.append(sub_query)
        if len(sub_queries) == 1:
            kvstore_query = sub_queries[0]
        else:
            kvstore_query = {'$and': sub_queries}
        logger.debug('kvstore query: %s' % kvstore_query)
        return kvstore_query

    @staticmethod
    def _build_regular_filter_query(name, value):
        if isinstance(value, list):
            query = {'$or': [EmEntity._build_single_value_query(name, val) for val in value]}
        else:
            query = EmEntity._build_single_value_query(name, value)
        return query

    @staticmethod
    def _build_dimension_filter_query(dim_name, dim_value):
        if isinstance(dim_value, list):
            query = {'$or': [EmEntity._build_single_dimension_value_query(dim_name, val) for val in dim_value]}
        else:
            query = EmEntity._build_single_dimension_value_query(dim_name, dim_value)
        return query

    @staticmethod
    def _build_single_dimension_value_query(dim_name, dim_value):
        dim_filter = '{}={}'.format(dim_name, dim_value)
        return EmEntity._build_single_value_query('dimensions_kv', dim_filter, em_common.ignore_case())

    @staticmethod
    def _build_single_value_query(name, value, ignore_case=True):
        kvstore_options = 'i' if ignore_case else ''
        kvstore_regexp = em_common.get_regex_search_string(value, kvstore_options)
        return {name: kvstore_regexp}

    @staticmethod
    def _build_status_query(value):
        if value.lower() == "active":
            query = {"expiry_time": {"$gte": int(time.time())}}
        else:
            query = {"expiry_time": {"$lt": int(time.time())}}
        return query
