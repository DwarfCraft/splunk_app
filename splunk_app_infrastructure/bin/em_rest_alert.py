# standard packages
import sys
from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_infrastructure', 'bin']))  # noqa
import em_path_inject  # noqa

import http.client

# app sepcific packages
from em_rest_alert_impl import EmAlertInterfaceImpl
from em_migration.migration_before_handle_hook import MigrationStatusCheckHook
# common packages
from logging_utils import log
from rest_handler import rest_interface_splunkd
from rest_handler.rest_interface_splunkd import route
from rest_handler.session import session
from rest_handler.hooks import before_handle_hooks

logger = log.getLogger()


@before_handle_hooks([MigrationStatusCheckHook])
class EmAlertInterface(rest_interface_splunkd.BaseRestInterfaceSplunkd):

    @route('/data', methods=['GET', 'POST'])
    def list_or_create_alerts(self, request):
        '''
        Use-cases:
            1. multiple alert definitions retrieval (GET)
            2. alert creation (POST)

        :param request an request object
        :return tuple<http status code, json response>
        '''
        if request.method == 'GET':
            interface_impl = EmAlertInterfaceImpl(session['authtoken'])
            logger.info('User triggered LIST alerts')
            response = interface_impl.handle_list_alerts(request)
            return http.client.OK, response
        else:
            # No user controls are needed here right now. Non-admin, non-power users will fail at
            # the alert creation step before the system authtoken is used.
            interface_impl = EmAlertInterfaceImpl(session['authtoken'],
                                                  session['global.system_authtoken'])
            logger.info('User triggered CREATE alert')
            alert = interface_impl.handle_create_alert(request)
            return http.client.CREATED, alert

    @route('/data/{alert_name}', methods=['GET', 'POST', 'DELETE'])
    def operate_on_single_alert(self, request, alert_name):
        '''
        Use-cases:
            1. individual alert data retrieval by alert name (GET)
            2. individual alert update for given alert name(POST)
            3. individual alert deletion by alert name (DELETE)

        :param request an request object
        :return tuple<http status code, json response>
        '''
        interface_impl = EmAlertInterfaceImpl(session['authtoken'])
        if request.method == 'GET':
            logger.info('User triggered GET for alert with name %s' % alert_name)
            response = interface_impl.handle_get_alert(request, alert_name)
            return http.client.OK, response
        elif request.method == 'POST':
            logger.info('User triggered UPDATE for alert with name %s' % alert_name)
            response = interface_impl.handle_update_alert(request, alert_name)
            return http.client.OK, response
        else:
            logger.info('User triggered DELETE for alert with name %s' % alert_name)
            response = interface_impl.handle_delete_alert(request, alert_name)
            return http.client.OK, response
