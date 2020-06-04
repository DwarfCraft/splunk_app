import em_path_inject  # noqa

from em_base_persistent_object import EMBasePersistentObject
from storage_mixins import ConfMixin
from solnlib.utils import is_true


MIGRATION_METADATA_CONF = 'sai_migration'


class MigrationMetadata(EMBasePersistentObject, ConfMixin):
    """
    MigrationMetadata represents the metadata of a finished or ongoing migration, including
    information like latest migrated version, if the process is running etc.
    """

    def __init__(self, key, latest_migrated_version, is_running):
        self.key = key
        self.latest_migrated_version = latest_migrated_version
        self.is_running = is_running

    @classmethod
    def storage_name(cls):
        return MIGRATION_METADATA_CONF

    @classmethod
    def _from_raw(cls, stanza):
        return MigrationMetadata(
            key=stanza['name'],
            latest_migrated_version=stanza['latest_migrated_version'],
            is_running=is_true(stanza['migration_running'])
        )

    def _raw(self):
        return {
            'latest_migrated_version': self.latest_migrated_version,
            'migration_running': self.is_running
        }

    @classmethod
    def get(cls):
        return super(MigrationMetadata, cls).get('metadata')
