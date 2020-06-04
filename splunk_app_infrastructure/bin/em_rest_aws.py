import sys
from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_infrastructure', 'bin']))  # noqa
import em_path_inject  # noqa

import http.client

# common packages
from em_rest_aws_impl import EMAwsInterfaceImpl
from em_migration.migration_before_handle_hook import MigrationStatusCheckHook

from logging_utils import log
from rest_handler import rest_interface_splunkd
from rest_handler.rest_interface_splunkd import route
from rest_handler.session import session
from rest_handler.hooks import before_handle_hooks

logger = log.getLogger()


@before_handle_hooks([MigrationStatusCheckHook])
class EMAwsInterface(rest_interface_splunkd.BaseRestInterfaceSplunkd):

    @route('/check_env', methods=['GET'])
    def handle_check_env(self, request):
        interface_impl = EMAwsInterfaceImpl(session['authtoken'])
        if request.method == 'GET':
            logger.info('User triggered AWS check env')
            response = interface_impl.handle_check_env(request)
            return http.client.OK, response
