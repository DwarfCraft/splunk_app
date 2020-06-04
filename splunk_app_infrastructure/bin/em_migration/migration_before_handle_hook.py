import em_path_inject  # noqa

from rest_handler.hooks import BeforeHandleHook
from rest_handler.exception import BaseRestException
from .em_model_migration_metadata import MigrationMetadata

import http.client


class MigrationRunningException(BaseRestException):
    def __init__(self):
        super(MigrationRunningException, self).__init__(
            http.client.SERVICE_UNAVAILABLE,
            'SAI is migrating to a new version'
        )


class MigrationStatusCheckHook(BeforeHandleHook):
    """
    MigrationStatusCheckHook checks if migration is currently running before requests handling. If
    migration is running, 503 (Service Unavailable) will be returned.
    """

    def before_handle(self, request):
        metadata = MigrationMetadata.get()
        if metadata.is_running:
            raise MigrationRunningException()
