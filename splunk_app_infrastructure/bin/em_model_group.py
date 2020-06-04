# Copyright 2019 Splunk Inc. All rights reserved.

from builtins import str
from builtins import object
from collections import Counter

from splunklib.client import Service
from storage_mixins import KVStoreMixin
from rest_handler.session import session
from logging_utils import log

from em_base_persistent_object import EMBasePersistentObject
import em_constants
import em_common
from em_search_manager import EMSearchManager
from em_model_entity import EmEntity
from em_correlation_filters import create_group_log_filter
from em_common import MONGODB_IGNORE_CASE, MONGODB_RESPECT_CASE

try:
    basestring
except NameError:
    basestring = str

logger = log.getLogger()


class InvalidGroupException(Exception):
    pass


class GroupAlreadyExistsException(Exception):
    pass


class GroupInternalException(Exception):
    pass


class GroupFilter(object):
    '''
    GroupFilter - represents the filter of a group, handles all the serialization and deserialization logic
    '''

    def __init__(self, filter):
        '''
        Initialize a gorup filter object

        :param filter: content of the group filter
        :type string OR dict: if string, must be in "a=b,c=d" format. if dict, must be in {"a":["b"], "c":["d"]} format.
        '''
        if isinstance(filter, basestring):
            self._filter = GroupFilter.convert_filter_string_to_dictionary(filter)
        elif isinstance(filter, dict):
            self._filter = filter
        else:
            raise InvalidGroupException('Invalid type for group filter: - %s' % type(filter))

    def __getitem__(self, key):
        return self._filter.get(key)

    def to_str(self, sort_by_key=True):
        return GroupFilter.convert_filter_dict_to_string(self._filter, sort_by_key=sort_by_key)

    def to_dict(self, key_prefix=None):
        rtval = self._filter
        if key_prefix is not None:
            rtval = {(key_prefix + key): val for key, val in self._filter.items()}
        return rtval

    def check_dims(self, entity_dims):
        '''
        Checks if the provided entity dimensions satisfy this group's filter.
        The dimensions match if they contain the key-value pair specified by the group filter.
        :type dims: dict
        :param dims: dimension to check
        :type filter_rule: dict
        :param filter_rule:

        :return: boolean
        '''
        ignore_case = em_common.ignore_case()

        for group_filter_dim_name, group_filter_dim_val in self._filter.items():
            group_filter_dim_val = [str(v).lower() if ignore_case else str(v)
                                    for v in group_filter_dim_val]
            entity_dim_vals = entity_dims.get(group_filter_dim_name)
            if not entity_dim_vals:
                return False
            if not isinstance(entity_dim_vals, list):
                entity_dim_vals = [entity_dim_vals]
            matched = False
            for val in entity_dim_vals:
                val = str(val).lower() if ignore_case else str(val)

                # check if record value is one of the filter values
                if val in group_filter_dim_val:
                    matched = True
                    break
                # otherwise check if record value matches any of the fuzzy match values
                fuzzy_matches = [v for v in group_filter_dim_val if v.endswith('*')]
                if len(fuzzy_matches):
                    matched = any(val.startswith(v[:-1]) for v in fuzzy_matches)
            if not matched:
                return False
        return True

    @staticmethod
    def convert_filter_string_to_dictionary(filter_string, append_key=''):
        """
        Convert the group filter string to
        to be a dict with dimension values as list
        for same dimension name.
        ie: input: 'os=linux,os=centos,location=usa'
            return: {'os': ['linux', 'centos'], 'location': ['usa']}
        :param filter_string
        :param append_key: key to use as prefix of keys in the returned dict.

        :return: dict
        """
        extracted_dimensions = {}
        if filter_string:
            for dimension in filter_string.split(','):
                key, value = dimension.strip().split('=')
                extracted_dimensions.setdefault('%s%s' % (append_key, key), set()).add(value)
        for dim, vals in extracted_dimensions.items():
            extracted_dimensions[dim] = list(vals)
        return extracted_dimensions

    @staticmethod
    def convert_filter_dict_to_string(filter_dict, append_key='', sort_by_key=True):
        filter_dict_keys = list(filter_dict.keys())
        if sort_by_key:
            filter_dict_keys.sort()

        res = []
        for k in filter_dict_keys:
            value = filter_dict[k]
            key = '{}{}'.format(append_key, k)
            if isinstance(value, str):
                res.append('{}={}'.format(key, value))
            elif isinstance(value, list):
                res.extend(['{}={}'.format(key, v) for v in value])
            else:
                raise InvalidGroupException('Invalid filter value type for key %s: %s' % (k, type(value)))
        return ','.join(res)

    def __repr__(self):
        return str(self._filter)


class EMGroup(EMBasePersistentObject, KVStoreMixin):
    """
    Group Model.

    Attributes:
        key: Primary key of group in KVStore.
        title: Title of group.
        filter: group filter object
        entities_count: count of entities in group
        active_entities_count: count of active entities in group
        inactive_entities_count: count of inactive entities in group
    """

    def __init__(self,
                 key,
                 title='',
                 filter='',
                 entities_count=0,
                 active_entities_count=0,
                 inactive_entities_count=0):
        """
        Return entity object
        """
        self.key = key
        self.title = title
        self.filter = GroupFilter(filter)
        self.entities_count = entities_count
        self.active_entities_count = active_entities_count
        self.inactive_entities_count = inactive_entities_count

    @classmethod
    def storage_name(cls):
        '''
        This method implements `storage_name` of `AbstractBaseStorageMixin`
        '''
        return em_constants.STORE_GROUPS

    @classmethod
    def _from_raw(cls, data):
        '''
        This method implements `_from_raw` of `EMBasePersistentObject`
        '''
        return EMGroup(
            key=data['_key'],
            title=data['title'],
            filter=data['filter'],
            entities_count=data.get('entities_count'),
            active_entities_count=data.get('active_entities_count'),
            inactive_entities_count=data.get('inactive_entities_count')
        )

    def _raw(self):
        '''
        This method implements `_raw` of `EMBasePersistentObject`
        '''
        return dict(
            _key=self.key,
            title=self.title,
            filter=self.filter.to_str(),
            entities_count=self.entities_count,
            active_entities_count=self.active_entities_count,
            inactive_entities_count=self.inactive_entities_count
        )

    def get_raw_data(self):
        """
        Get raw dict object from this entity
        """
        return self._raw()

    @classmethod
    def load(cls, count, offset, sort_key, sort_dir, query=None, options=MONGODB_IGNORE_CASE):
        '''
        Load groups based on input parameters

        :param count: how many groups to load
        :type int
        :param offset: starting offset of groups to load
        :type int
        :param sort_key: key based on which the result is sorted (note: sorting is done before count and offset)
        :type str
        :param sort_dir: sort direction, can be either 'asc' or 'desc'
        :type str
        :param query: a filter query in {<key>: [<value>, <value>...]} format
        :type dict

        :return a list of EMGroup objects
        :rtype list
        '''
        sort_param = []
        if sort_key:
            sort_param = [(sort_key, sort_dir)]
        # convert filter dict query format to kvstore query
        kvstore_query = None
        if query:
            kvstore_query = em_common.convert_query_params_to_mongoDB_query(query, options)
        return super(EMGroup, cls).load(
            limit=count,
            skip=offset,
            sort_keys_and_orders=sort_param,
            fields='',
            query=kvstore_query
        )

    @classmethod
    def load_filter_by_entity_ids(cls, entity_ids):
        '''
        load groups that contain entities corresponding to the input entity ids
        :type entity_ids: list of str
        :param entity_ids: list of entity ids

        :rtype list
        :return list of EMGroup objects
        '''
        search_manager = EMSearchManager(em_common.get_server_uri(), session['authtoken'], em_constants.APP_NAME)
        groups_with_count = search_manager.filter_groups_by_entity_ids(entity_ids)
        group_keys = list(groups_with_count)
        if len(group_keys):
            return EMGroup.load(0, 0, '', 'asc', query={'_key': group_keys})
        return []

    @classmethod
    def create(cls, title, group_filter):
        '''
        Create a group

        :param title: title of the group to be created
        :param filter: filter of the group to be created in string format. E.g. 'a=1,b=2'
        '''
        EMGroup.check_title_validity(title)
        data = {
            'title': title,
            'filter': group_filter
        }
        new_group = super(EMGroup, cls).create(data)
        new_group.update_metadata()
        new_group.save()
        return new_group

    def update(self):
        EMGroup.check_title_validity(self.title, except_for_group_key=self.key)
        self.update_metadata()
        self.save()

    @classmethod
    def check_title_validity(cls, title, except_for_group_key=None):
        '''
        Checks if title for a group is valid or not

        :param title: title of the group to be checked
        :param except_for_group_key: if the group with the same title is the same as the input exception key,
                                     then do not raise an exception
        '''
        if not title:
            raise InvalidGroupException('Group title should not be empty')
        if '|' in title or '=' in title:
            raise InvalidGroupException('Group title contains invalid character(s)')

        groups_with_same_title = EMGroup.load(0, 0, '', 'asc', query={'title': [title]}, options=MONGODB_RESPECT_CASE)
        if len(groups_with_same_title):
            if except_for_group_key is not None and groups_with_same_title[0].key == except_for_group_key:
                return
            raise GroupAlreadyExistsException('Group with title %s already exists' % title)

    def update_metadata(self):
        '''
        Compute and update metadata of the group object (does not persist to storage)
        '''
        entities = self.get_entities()
        entity_status_breakdown = Counter(en.status for en in entities)
        self.entities_count = len(entities)
        self.active_entities_count = entity_status_breakdown.get(EmEntity.ACTIVE, 0)
        self.inactive_entities_count = entity_status_breakdown.get(EmEntity.INACTIVE, 0)

    @classmethod
    def bulk_delete(cls, delete_filter_dict=None, exclusion_list=None):
        '''
        Bulk delete groups specified by delete_filter_dict, if delete_filter_dict is None then delete all groups
        This method will also delete any associated alerts of the deleted groups

        :param delete_filter_dict: a entity filter dict that specifies the groups to delete. e.g. {'_key': ['a', 'b']}
        :param exclusion_list: a list of keys of groups that should *NOT* be deleted
        '''
        # build exclusion query
        exclusion_list = [] if exclusion_list is None else exclusion_list
        exclusion_query = None
        if len(exclusion_list):
            exclusion_filter = {'_key': exclusion_list}
            exclusion_query = em_common.negate_special_mongo_query(
                em_common.convert_query_params_to_mongoDB_query(exclusion_filter, MONGODB_RESPECT_CASE))

        # build delete query
        delete_filter_dict = {} if delete_filter_dict is None else delete_filter_dict
        filter_delete_query = em_common.convert_query_params_to_mongoDB_query(delete_filter_dict, MONGODB_RESPECT_CASE)

        if exclusion_query is None:
            delete_query = filter_delete_query
        else:
            delete_query = {'$and': [filter_delete_query, exclusion_query]}

        # get key of groups to be deleted
        groups_to_delete = super(EMGroup, cls).load(
            limit=0, skip=0, sort_keys_and_orders=[], fields='', query=delete_query
        )
        group_keys_to_delete = [group.key for group in groups_to_delete]

        # bulk delete groups
        if len(group_keys_to_delete):
            cls.storage_bulk_delete(delete_query)
            # bulk delete all associated alert savedsearch
            svc = Service(token=session['authtoken'], app=em_constants.APP_NAME, owner='nobody')
            for alert_ss in svc.saved_searches.iter(
                search=' OR '.join(
                    'alert.managedBy={}:{}'.format(em_constants.APP_NAME, key) for key in group_keys_to_delete
                )
            ):
                logger.info('bulk delete cleanup - deleting alert %s' % alert_ss.name)
                alert_ss.delete()

    def check_entity_membership(self, entity):
        """
        Check if entity belongs to current group
        :type entity: an EmEntity object
        :param entity: an entity object

        :return: boolean
        """
        return self.filter.check_dims(entity.dimensions)

    def get_entities(self):
        '''
        Get a list of entities that are members of this group
        '''
        return EmEntity.load(0, 0, 'title', 'asc', query=self.filter.to_dict(key_prefix='dimensions.'))

    def get_correlation_filter(self):
        '''
        Get correlation filter that can be used to correlate events with metrics
        associated with this group.
        '''
        entities = self.get_entities()

        entities_by_class = {}
        related_entity_cls = []
        for ent in entities:
            entity_class = ent.get_entity_class_info()
            if entity_class.key in entities_by_class:
                entities_by_class[entity_class.key].append(ent)
            else:
                entities_by_class[entity_class.key] = [ent]
                related_entity_cls.append(entity_class)

        correlation_filter = create_group_log_filter(entities_by_class, related_entity_cls)
        return correlation_filter
