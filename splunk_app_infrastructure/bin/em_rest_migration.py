import sys
from splunk.clilib.bundle_paths import make_splunkhome_path
sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_infrastructure', 'bin']))  # noqa
import em_path_inject  # noqa

import http.client

# common packages
from logging_utils import log
from rest_handler import rest_interface_splunkd
from rest_handler.rest_interface_splunkd import route, BaseRestException

from em_migration.em_model_migration_metadata import MigrationMetadata

logger = log.getLogger()


class MigrationMetadataInternalException(BaseRestException):
    def __init__(self, msg):
        super(MigrationMetadataInternalException, self).__init__(http.client.INTERNAL_SERVER_ERROR, msg)


class EmMigrationInterface(rest_interface_splunkd.BaseRestInterfaceSplunkd):

    @route('/status', methods=['GET'])
    def get_migration_status(self, request):
        metadata = MigrationMetadata.get()
        if metadata is None:
            raise MigrationMetadataInternalException('migration status could not be read')

        logger.info('User triggered GET on migration status - migration in progress: %s' % metadata.is_running)
        return http.client.OK, {
            'in_progress': metadata.is_running
        }
