# Copyright 2019 Splunk Inc. All rights reserved.
import em_path_inject  # noqa
from builtins import object
import json
import http.client
from logging_utils import log
from rest_handler.exception import BaseRestException
from em_correlation_filters import serialize
from em_model_group import EMGroup, GroupFilter, GroupAlreadyExistsException, InvalidGroupException

logger = log.getLogger()


class GroupInternalException(BaseRestException):
    def __init__(self, msg):
        super(GroupInternalException, self).__init__(http.client.INTERNAL_SERVER_ERROR, msg)


class GroupNotFoundException(BaseRestException):
    def __init__(self, msg):
        super(GroupNotFoundException, self).__init__(http.client.NOT_FOUND, msg)


class GroupArgValidationException(BaseRestException):
    def __init__(self, msg):
        super(GroupArgValidationException, self).__init__(http.client.BAD_REQUEST, msg)


class EmGroupsInterfaceImpl(object):

    def __init__(self, session_key):
        self.session_key = session_key

    def handle_get_group(self, request, group_id):
        group = EMGroup.get(group_id)
        if group is None:
            raise GroupNotFoundException('Group with id %s not found' % group_id)
        correlation_filter = group.get_correlation_filter()
        entities = group.get_entities()

        response = self.extract_group_json_response(group)
        response.update({
            'correlation_filter': serialize(correlation_filter),
            'entities_in_group': [
                {'_key': ent.key, 'title': ent.title, 'status': ent.status} for ent in entities
            ]
        })
        return response

    def handle_list_groups(self, request):
        count = int(request.query.get('count', 0))
        offset = int(request.query.get('offset', 0))
        sort_key = request.query.get('sort_key', 'title')
        sort_dir = request.query.get('sort_dir', 'asc')
        query = json.loads(request.query.get('query', '{}'))
        filter_entity_ids = json.loads(request.query.get('filter_by_entity_ids', '[]'))
        if len(filter_entity_ids):
            groups = EMGroup.load_filter_by_entity_ids(filter_entity_ids)
        else:
            groups = EMGroup.load(count, offset, sort_key, sort_dir, query)
        response = [self.extract_group_json_response(group) for group in groups]
        return response

    def handle_create_group(self, request):
        try:
            group_title = request.data.get('title', '')
            group_filter = request.data.get('filter', '')
            group = EMGroup.create(group_title, group_filter)
            return self.extract_group_json_response(group)
        except (InvalidGroupException, GroupAlreadyExistsException) as e:
            raise GroupArgValidationException('%s' % e)

    def handle_update_group(self, request, group_id):
        group = EMGroup.get(group_id)
        if group is None:
            raise GroupNotFoundException('Group with id %s not found' % group_id)
        try:
            new_title = request.data.get('title')
            new_filter = request.data.get('filter')
            if new_title:
                group.title = new_title
            if new_filter is not None:
                group.filter = GroupFilter(new_filter)
            group.update()
            return self.extract_group_json_response(group)
        except (InvalidGroupException, GroupAlreadyExistsException) as e:
            raise GroupArgValidationException('%s' % e)

    def handle_delete(self, request, group_id):
        query = {'_key': [group_id]}
        EMGroup.bulk_delete(query)

    def handle_bulk_delete(self, request):
        query = json.loads(request.query.get('query', '{}'))
        exclusion_list = json.loads(request.query.get('exclusion_list', '[]'))
        EMGroup.bulk_delete(query, exclusion_list=exclusion_list)

    def handle_get_titles_summary(self, request):
        query = json.loads(request.query.get('query', '{}'))
        groups = EMGroup.load(0, 0, '', 'asc', query=query)
        return {
            'titles': [group.title for group in groups]
        }

    def handle_count(self, request):
        query = json.loads(request.query.get('query', '{}'))
        groups = EMGroup.load(0, 0, '', 'asc', query)
        return {
            'total_count': len(groups)
        }

    @staticmethod
    def extract_group_json_response(group):
        return {
            '_key': group.key,
            'title': group.title,
            'filter': group.filter.to_dict(),
            'entities_count': group.entities_count,
            'active_entities_count': group.active_entities_count,
            'inactive_entities_count': group.inactive_entities_count
        }
