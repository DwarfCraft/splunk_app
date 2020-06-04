# standard packages
try:
    import http.client as httplib
except ImportError:
    import httplib
import sys
from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_infrastructure', 'bin']))  # noqa
# app sepcific packages
from em_rest_entity_impl import EmEntityInterfaceImpl
from em_migration.migration_before_handle_hook import MigrationStatusCheckHook
# common packages
import em_path_inject  # noqa
from logging_utils import log
from rest_handler import rest_interface_splunkd
from rest_handler.rest_interface_splunkd import route
from rest_handler.session import session
from rest_handler.hooks import before_handle_hooks

logger = log.getLogger()


@before_handle_hooks([MigrationStatusCheckHook])
class EmEntityInterface(rest_interface_splunkd.BaseRestInterfaceSplunkd):

    @route('/data', methods=['GET'])
    def load_entities(self, request):
        '''
        this handler handles:
            1. multiple or all entities data retrieval (GET)

        :param request an request object
        :return tuple<http status code, json response>
        '''
        interface_impl = EmEntityInterfaceImpl(session['authtoken'])
        logger.info('User triggered LOAD entities')
        response = interface_impl.handle_load(request)
        return httplib.OK, response

    @route('/data/{entity_id}', methods=['GET', 'DELETE'])
    def get_entity(self, request, entity_id):
        interface_impl = EmEntityInterfaceImpl(session['authtoken'])
        if request.method == 'GET':
            logger.info('User triggered GET entity')
            response = interface_impl.handle_get(request, entity_id)
            return httplib.OK, response
        elif request.method == 'DELETE':
            logger.info('User triggered DELETE entity')
            response = interface_impl.handle_delete(request, entity_id)
            return httplib.NO_CONTENT, response

    @route('/bulk_delete', methods=['DELETE'])
    def bulk_delete_entities(self, request):
        interface_impl = EmEntityInterfaceImpl(session['authtoken'])
        logger.info('User triggered BULK DELETE entities')
        response = interface_impl.handle_bulk_delete(request)
        return httplib.NO_CONTENT, response

    @route('/metadata', methods=['GET'])
    def get_metadata(self, request):
        interface_impl = EmEntityInterfaceImpl(session['authtoken'])
        logger.info('User triggered GET entity metdata')
        response = interface_impl.handle_metadata(request)
        return httplib.OK, response

    @route('/dimension_summary', methods=['GET'])
    def get_dimension_summary(self, request):
        interface_impl = EmEntityInterfaceImpl(session['authtoken'])
        logger.info('User triggered GET dimensions summary')
        response = interface_impl.handle_dimension_summary(request)
        return httplib.OK, response

    @route('/metric_name', methods=['GET'])
    def get_metric_names(self, request):
        interface_impl = EmEntityInterfaceImpl(session['authtoken'])
        logger.info('User triggered GET metric names')
        response = interface_impl.handle_metric_names(request)
        return httplib.OK, response

    @route('/metric_data', methods=['GET'])
    def handle_entity_metric_data(self, request):
        interface_impl = EmEntityInterfaceImpl(session['authtoken'])
        logger.info('User triggered GET metric data')
        response = interface_impl.handle_metric_data(request)
        return httplib.OK, response
