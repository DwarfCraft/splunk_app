import sys
from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_infrastructure', 'bin']))  # noqa
import em_path_inject  # noqa

import http.client

from em_rest_groups_impl import EmGroupsInterfaceImpl
from em_migration.migration_before_handle_hook import MigrationStatusCheckHook
# common packages
from logging_utils import log
from rest_handler import rest_interface_splunkd
from rest_handler.rest_interface_splunkd import route
from rest_handler.hooks import before_handle_hooks
from rest_handler.session import session

logger = log.getLogger()


@before_handle_hooks([MigrationStatusCheckHook])
class EmGroupsInterface(rest_interface_splunkd.BaseRestInterfaceSplunkd):

    @route('/data', methods=['GET', 'POST'])
    def list_or_create_group(self, request):
        interface_impl = EmGroupsInterfaceImpl(session['authtoken'])
        if request.method == 'GET':
            logger.info('User triggered list groups')
            response = interface_impl.handle_list_groups(request)
            return http.client.OK, response
        elif request.method == 'POST':
            logger.info('User triggered create group')
            group = interface_impl.handle_create_group(request)
            return http.client.CREATED, group

    @route('/data/{group_id}', methods=['GET', 'POST', 'DELETE'])
    def operate_on_single_group(self, request, group_id):
        interface_impl = EmGroupsInterfaceImpl(session['authtoken'])
        if request.method == 'GET':
            logger.info('User triggered get group with key %s' % group_id)
            response = interface_impl.handle_get_group(request, group_id)
            return http.client.OK, response
        elif request.method == 'POST':
            logger.info('User triggered update group with key %s' % group_id)
            response = interface_impl.handle_update_group(request, group_id)
            return http.client.OK, response
        elif request.method == 'DELETE':
            logger.info('User triggered delete group with key %s' % group_id)
            response = interface_impl.handle_delete(request, group_id)
            return http.client.NO_CONTENT, response

    @route('/metadata', methods=['GET'])
    def handle_group_metadata(self, request):
        interface_impl = EmGroupsInterfaceImpl(session['authtoken'])
        logger.info('User requested metadata for group')
        response = interface_impl.handle_get_titles_summary(request)
        return http.client.OK, response

    @route('/count', methods=['GET'])
    def handle_group_metadata_count(self, request):
        interface_impl = EmGroupsInterfaceImpl(session['authtoken'])
        logger.info('User requested count for group')
        response = interface_impl.handle_count(request)
        return http.client.OK, response

    @route('/bulk_delete', methods=['DELETE'])
    def handle_entity_bulk_delete(self, request):
        interface_impl = EmGroupsInterfaceImpl(session['authtoken'])
        logger.info('User triggered bulk delete on groups')
        response = interface_impl.handle_bulk_delete(request)
        return http.client.NO_CONTENT, response
