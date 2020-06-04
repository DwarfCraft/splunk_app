# Environment configuration
import sys
from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_infrastructure', 'bin']))  # noqa
import em_path_inject # noqa
import http.client
# App specific packages
from em_rest_subscriptions_impl import EmSubscriptionsInterfaceImpl
from em_migration.migration_before_handle_hook import MigrationStatusCheckHook
# Common packages
from logging_utils import log
from rest_handler import rest_interface_splunkd
from rest_handler.rest_interface_splunkd import route
from rest_handler.session import session
from rest_handler.hooks import before_handle_hooks

logger = log.getLogger()


@before_handle_hooks([MigrationStatusCheckHook])
class EmSubscriptionsInterface(rest_interface_splunkd.BaseRestInterfaceSplunkd):

    @route('/data', methods=['GET'])
    def list_subscriptions(self, request):
        interface_impl = EmSubscriptionsInterfaceImpl(session['global.system_authtoken'])
        logger.info('User triggered list subscriptions')
        response = interface_impl.handle_list_subscriptions()
        return http.client.OK, response
