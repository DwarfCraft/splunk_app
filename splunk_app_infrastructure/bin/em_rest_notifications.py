import sys
from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_infrastructure', 'bin']))  # noqa

import em_path_inject  # noqa
from logging_utils import log
import rest_handler.rest_interface_splunkd as rest_interface_splunkd
from rest_handler.rest_interface_splunkd import route
from rest_handler.session import session
from rest_handler.hooks import before_handle_hooks
from rest_handler.exception import BaseRestException

from em_migration.migration_before_handle_hook import MigrationStatusCheckHook
from authentication_before_rest_hook import AuthenticationRestHook
from em_rest_notifications_impl import EmVictorOpsInterfaceImpl, EmWebhookInterfaceImpl, EmSlackInterfaceImpl
import http.client

logger = log.getLogger()


class NotificationAuthorizationException(BaseRestException):
    def __init__(self, msg):
        super(NotificationAuthorizationException, self).__init__(http.client.UNAUTHORIZED, msg)


@before_handle_hooks([MigrationStatusCheckHook, AuthenticationRestHook])
class EmNotificationsInterface(rest_interface_splunkd.BaseRestInterfaceSplunkd):

    def _check_power_or_greater(self):
        roles = session['roles']
        if ('admin' not in roles and 'sc_admin' not in roles and 'power' not in roles):
            raise NotificationAuthorizationException(
                'Unauthorized - User must have "admin", "sc_admin" or "power" role.')

    def _check_admin_or_sc_admin(self):
        roles = session['roles']
        if ('admin' not in roles and 'sc_admin' not in roles):
            raise NotificationAuthorizationException('Unauthorized - User must have "admin" or "sc_admin" role.')

    @route('/custom_notifications_webhook/data', methods=['GET', 'POST'])
    def get_or_create_default_custom_webhook_url(self, request):
        interface_impl = EmWebhookInterfaceImpl(session['authtoken'])
        if request.method == 'GET':
            self._check_power_or_greater()
            logger.info('user triggered get default webhook url')
            response = interface_impl.handle_get(request)
        elif request.method == 'POST':
            self._check_admin_or_sc_admin()
            logger.info('user triggered update default webhook url')
            response = interface_impl.handle_update(request)
        return response

    @route('/slack/data', methods=['GET', 'POST'])
    def get_or_create_default_slack_webhook_url(self, request):
        interface_impl = EmSlackInterfaceImpl(session['authtoken'])
        if request.method == 'GET':
            self._check_power_or_greater()
            logger.info('user triggered get slack default webhook url')
            response = interface_impl.handle_get(request)
        elif request.method == 'POST':
            self._check_admin_or_sc_admin()
            logger.info('user triggered update slack default webhook url')
            response = interface_impl.handle_update(request)
        return response

    @route('/victorops/data', methods=['GET', 'POST'])
    def list_or_create_victorops(self, request):
        interface_impl = EmVictorOpsInterfaceImpl(session['authtoken'])
        if request.method == 'GET':
            self._check_power_or_greater()
            logger.info('user triggered list victorops')
            vos = interface_impl.handle_list(request)
            return http.client.OK, vos[0].raw() if len(vos) else {}
        else:
            self._check_admin_or_sc_admin()
            logger.info('user triggered create victorops')
            vo = interface_impl.handle_create(request)
            return http.client.CREATED, vo.raw()

    @route('/victorops/data/{vo_id}', methods=['GET', 'POST', 'DELETE'])
    def operate_single_vo(self, request, vo_id):
        interface_impl = EmVictorOpsInterfaceImpl(session['authtoken'])
        if request.method == 'GET':
            self._check_power_or_greater()
            logger.info('user triggered get victorops')
            vo = interface_impl.handle_get(request, vo_id)
            return http.client.OK, vo.raw()
        elif request.method == 'POST':
            self._check_admin_or_sc_admin()
            logger.info('user triggered update victorops')
            vo = interface_impl.handle_edit(request, vo_id)
            return http.client.OK, vo.raw()
        else:
            self._check_admin_or_sc_admin()
            logger.info('user triggered delete victorops')
            res = interface_impl.handle_remove(request, vo_id)
            if res:
                return http.client.OK, {}
