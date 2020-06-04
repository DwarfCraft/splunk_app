import em_path_inject # noqa
import os
import sys
import traceback
from future.moves.urllib.parse import quote
import tarfile
import time

import em_common
import em_constants
import em_utils
from em_migration import migration_handlers_dict, BaseMigrationHandler
from em_migration.em_model_migration_metadata import MigrationMetadata
from em_migration.process_control import (
    NonMigrationDataInputsController,
    SavedsearchController,
    ProcessControlInternalException
)
from modinput_wrapper.base_modularinput import BaseModularInput
from rest_handler.session import session
from service_manager.splunkd.conf import ConfManager
from splunk import getDefault
from splunk.clilib.bundle_paths import make_splunkhome_path
from splunklib.client import Service
from logging_utils import log

APP_CONF_FILE = 'app'
BACKUP_DIR_NAME = 'migration_backup'


class KnownMigrationException(Exception):
    def __init__(self, msg):
        super(KnownMigrationException, self).__init__(msg)


class EMMigrationController(BaseModularInput):
    app = em_constants.APP_NAME
    name = 'sai_migration_controller'
    title = 'Splunk App for Infrastructure - Version Migration Controller'
    description = 'Modular input to handle SAI migrations from the previous ' + \
        'version to the current version'
    use_external_validation = False
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    use_single_instance = True

    def __init__(self):
        super(EMMigrationController, self).__init__()

    def do_additional_setup(self):
        log_level = self.inputs.get('job').get('log_level', 'INFO')
        self.logger = log.getLogger(logger_name=self.name,
                                    log_level=log_level)
        self.check_kvstore_readiness()
        self.session_key = session['authtoken']
        self.dry_run = self.inputs.get('job').get('dry_run', '').lower() in ('1', 'true')
        server_uri = em_common.get_server_uri()
        self.splunkd_service = Service(
            port=getDefault('port'),
            token=self.session_key,
            owner='nobody',
            app=em_constants.APP_NAME,
        )
        self.app_conf_manager = ConfManager(
            conf_file=APP_CONF_FILE,
            server_uri=server_uri,
            session_key=self.session_key,
            app=em_constants.APP_NAME
        )
        self.migration_metadata = MigrationMetadata.get()
        self.current_version = self.migration_metadata.latest_migrated_version
        self.new_version = self.app_conf_manager.get_stanza('launcher')['entry'][0]['content']['version']
        self.data_inputs_controller = NonMigrationDataInputsController()
        self.savedsearch_controller = SavedsearchController()

    @property
    def current_version(self):
        return self._current_version

    @current_version.setter
    def current_version(self, version):
        self.migration_metadata.latest_migrated_version = version
        self.migration_metadata.save()
        self._current_version = version

    def do_execute(self):
        migration_started = False
        try:
            # Only run on the search head captain in a search head cluster
            if not em_common.modular_input_should_run(self.session_key):
                self.logger.info('SAI migration skipped on non-search head captain in search head cluster')
                return

            # initialize latest migrated version
            if self.current_version == '?.0.0' and self.is_fresh_installation():
                self.current_version = self.new_version

            if self.current_version != self.new_version:
                migration_started = True
                self.set_migration_running_status(running=True)
                self.backup_app()
                self.disable_non_migration_processes()

                for version in migration_handlers_dict:
                    if self.current_version == '?.0.0' or em_utils.is_lower_version(self.current_version, version):
                        self.execute_migration(version)
                        self.current_version = version

                # ensure that the latest migrated version is the latest app version even
                # when there's no migration needed for new version
                self.current_version = self.new_version
                self.post_migration_success_message()

        except KnownMigrationException as e:
            self.logger.error(e)
            self.post_migration_failure_message(e)
        # Unknown migration errors
        except Exception as e:
            self.logger.error('Failed to migrate to version %s - Error: %s' % (self.new_version, e))
            self.logger.debug(traceback.format_exc())
            query = quote('index=_internal source="*%s.log*"' % self.name)
            search_link = 'Check [[/app/splunk_app_infrastructure/search?q=%s|SAI migration logs]] for details' % query
            self.post_migration_failure_message(search_link)
        finally:
            if migration_started:
                self.set_migration_running_status(running=False)
                self.enable_non_migration_processes()

    def check_kvstore_readiness(self):
        try:
            em_common.check_kvstore_readiness(session['authtoken'])
        except em_common.KVStoreNotReadyException as e:
            self.logger.error('Migration failed because KVStore is not ready - Error: %s' % e)
            query = quote('index=_internal source="*%s.log*"' % self.name)
            search_link = 'Check [[/app/splunk_app_infrastructure/search?q=%s|SAI migration logs]] for details' % query
            fail_message = 'SAI migration failed because KVStore is not ready. %s' % search_link
            self.post_message('error', fail_message)
            sys.exit(1)

    def is_fresh_installation(self):
        entity_store = self.splunkd_service.kvstore['em_entities'].data
        group_store = self.splunkd_service.kvstore[em_constants.STORE_GROUPS].data
        entities = entity_store.query(limit=1)
        groups = group_store.query(limit=1)
        de_entity_store = self.splunkd_service.kvstore[em_constants.STORE_ENTITY_CACHE].data
        de_entities = de_entity_store.query(limit=1)
        # if there's no entities and no groups, there should be no alerts
        return len(entities) == 0 and len(groups) == 0 and len(de_entities) == 0

    def set_migration_running_status(self, running):
        """
        Update migration status that indicates if migration is ongoing

        :param running - boolean indicating if migration is running
        :type boolean
        """
        if not isinstance(running, bool):
            raise KnownMigrationException('Invalid migration status set')
        self.migration_metadata.is_running = int(running)
        self.migration_metadata.save()

    def backup_app(self):
        """
        Create a backup tarball of the app's local configurations
        """
        self.logger.info('Start creating backup of existing app installation...')

        sai_app_path = make_splunkhome_path(['etc', 'apps', em_constants.APP_NAME])
        backup_folder = os.path.join(sai_app_path, BACKUP_DIR_NAME)
        backup_file_path = os.path.join(backup_folder, 'sai_app_backup_%d.tgz' % time.time())

        if not os.path.exists(backup_folder):
            os.makedirs(backup_folder)

        with tarfile.open(backup_file_path, 'w:gz') as tar:
            local_conf_dir = os.path.join(sai_app_path, 'local')
            local_meta = os.path.join(sai_app_path, 'metadata', 'local.meta')
            tar.add(local_conf_dir, recursive=True, arcname=os.path.join(em_constants.APP_NAME, 'local'))
            tar.add(local_meta, recursive=True, arcname=os.path.join(em_constants.APP_NAME, 'metadata', 'local.meta'))

        self.post_message(
            'info',
            'SAI is migrating to version %s. Saved backup of current version at %s.' % (
                self.new_version,
                os.path.join('$SPLUNK_HOME', 'etc', 'apps', em_constants.APP_NAME, BACKUP_DIR_NAME)
            )
        )
        self.logger.info('Created backup file of existing app installation at %s.' % backup_file_path)

    def disable_non_migration_processes(self):
        self.data_inputs_controller.disable()
        self.savedsearch_controller.disable()

    def enable_non_migration_processes(self):
        try:
            self.data_inputs_controller.enable()
            self.savedsearch_controller.enable()
        except ProcessControlInternalException as e:
            self.logger.error('Failed to re-enable non-migration processes - Error: %s' % e)
            self.post_message(
                'warn',
                'Failed to enable processes that were disabled during migration. Please re-enable them manually.'
            )

    def execute_migration(self, migrate_to_version):
        """
        Executes migration handlers for the input target version

        :param migrate_to_version - target version to migrate to
        :type string
        """
        migration_dict = migration_handlers_dict.get(migrate_to_version, {})
        # default minimal version to 1.0.0, versions before that are not supported
        minimal_version = migration_dict.get('minimal_version', '1.0.0')
        migration_handlers = migration_dict.get('handlers', [])

        if not self.should_execute(migrate_to_version, minimal_version, migration_handlers):
            self.logger.info('No migration needs to be applied from version %s to %s, skipping...' % (
                self.current_version,
                migrate_to_version
            ))
            return

        self.logger.info('Starting SAI migration from version %s to %s...' % (self.current_version, migrate_to_version))
        for handler_cls in migration_handlers:
            migration_handler_obj = handler_cls(self.logger, self.session_key)
            migration_handler_obj.execute(dry_run=self.dry_run)
        if self.dry_run:
            self.logger.info('SAI tested migration from version %s to %s. No changes have been applied.' % (
                self.current_version,
                migrate_to_version
            ))
        else:
            self.logger.info('SAI migration from version %s to %s succeeded' % (
                self.current_version,
                migrate_to_version
            ))

    def should_execute(self, migrate_to_version, minimal_version, migration_handlers):
        # Check if there was an error in loading versions
        if not self.current_version:
            raise KnownMigrationException('Migration unable to identify app version')

        # check if version satisfies minimal version
        if self.current_version != '?.0.0' and em_utils.is_lower_version(self.current_version, minimal_version):
            raise KnownMigrationException('Migration cannot migrate from this base version')

        if len(migration_handlers) == 0:
            return False

        # Check that each migration in the migration handler is supported by this version
        for handler_cls in migration_handlers:
            if not issubclass(handler_cls, BaseMigrationHandler):
                raise KnownMigrationException('Migration handler of invalid type found')
        return self.current_version != migrate_to_version

    def post_migration_success_message(self):
        success_msg = 'SAI successfully migrated to version %s' % self.new_version
        self.post_message('info', success_msg)

    def post_migration_failure_message(self, complementary_message):
        backup_dir_path = os.path.join('$SPLUNK_HOME', 'etc', 'apps', em_constants.APP_NAME, BACKUP_DIR_NAME)
        fail_message = 'SAI failed to migrate to version %s. %s. Saved backup of old version at %s.' % (
            self.new_version,
            complementary_message,
            backup_dir_path
        )
        self.post_message('error', fail_message)

    def post_message(self, severity, message):
        self.splunkd_service.messages.create(
            '[SAI migration]',
            severity=severity,
            value=message
        )


if __name__ == '__main__':
    instance = EMMigrationController()
    instance.execute()
