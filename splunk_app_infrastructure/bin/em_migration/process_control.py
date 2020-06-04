import em_path_inject  # noqa

from splunk import getDefault
from splunklib.client import Service
from solnlib.utils import retry, is_true
from rest_handler.session import session
from logging_utils.log import getLogger
from storage_mixins import KVStoreMixin

import em_constants
from em_base_persistent_object import EMBasePersistentObject

from future.moves.urllib.error import HTTPError
import time

logger = getLogger()


class ProcessControlInternalException(Exception):
    pass


class MigrationProcessControlCheckpoint(EMBasePersistentObject, KVStoreMixin):
    """
    MigrationProcessControlCheckpiont - a checkpoint record where the changes made to processes are
    recorded and persisted to disk to avoid information loss upon migration process crash.
    """

    STORE_MIGRATION_PROCESS_CONTROL_RECORD = 'em_migration_process_control_checkpoint'

    def __init__(self, key, mutated_savedsearches=None):
        self.key = key
        self.mutated_savedsearches = mutated_savedsearches if mutated_savedsearches else []

    @classmethod
    def storage_name(cls):
        return cls.STORE_MIGRATION_PROCESS_CONTROL_RECORD

    @classmethod
    def _from_raw(cls, data):
        return MigrationProcessControlCheckpoint(
            key=data['_key'],
            mutated_savedsearches=data['mutated_savedsearches']
        )

    def _raw(self):
        return {'mutated_savedsearches': self.mutated_savedsearches}

    @classmethod
    @retry(exceptions=[HTTPError])
    def get_or_create(cls):
        existing_checkpoint = super(MigrationProcessControlCheckpoint, cls).get('record')
        if existing_checkpoint is None:
            checkpoint = MigrationProcessControlCheckpoint.create({
                '_key': 'record',
                'mutated_savedsearches': []
            })
            return checkpoint
        return existing_checkpoint

    def make_mutated_savedsearch(self, savedsearch_name, initial_state, final_state):
        return {
            'name': savedsearch_name,
            'initial_state': initial_state,
            'final_state': final_state,
            'mod_time': time.time()
        }

    @retry(exceptions=[HTTPError])
    def report_savedsearch_change(self, savedsearch_name, initial_state, final_state):
        logger.info('Reporting savedsearch %s changes to checkpoint...' % savedsearch_name)
        savedsearch_in_list = False
        mutated_search = self.make_mutated_savedsearch(savedsearch_name, initial_state, final_state)
        for mutated_savedsearch in self.mutated_savedsearches:
            if mutated_savedsearch['name'] == savedsearch_name:
                savedsearch_in_list = True
                break
        if not savedsearch_in_list:
            self.mutated_savedsearches.append(mutated_search)
            self.save()

    def clear_savedsearches_checkpoint(self):
        logger.info('Clearing savedsearches checkpoint...')
        self.mutated_savedsearches = []
        self.save()

    def get_mutated_savedsearch(self, name):
        for mutated_search in self.mutated_savedsearches:
            if mutated_search['name'] == name:
                return mutated_search
        return None


class NonMigrationDataInputsController(object):
    """
    NonMigrationDataInputsController enable/disable data inputs that are not
    associated with the migration process in order to avoid them interrupting the migration process.
    """

    # NOTE: this list of inputs need to be updated with whatever inputs that the current version of
    # the SAI app has that might interfere with the migration process
    data_inputs_list = [
        ('em_entity_migration', 'job'),
        ('aws_input_restarter', 'restarter'),
        ('em_entity_class_manager', 'job'),
        ('em_group_metadata_manager', 'job')
    ]

    def __init__(self):
        self.svc = Service(port=getDefault('port'),
                           token=session['authtoken'],
                           app=em_constants.APP_NAME,
                           owner='nobody')

    def enable(self):
        """
        Enables all non-migration related data inputs (that were previous disabled with the `disabled` call)
        """
        self._enable_disable_data_inputs('enable')

    def disable(self):
        """
        Disables all non-migration related data inputs
        """
        self._enable_disable_data_inputs('disable')

    @retry(exceptions=[HTTPError])
    def _enable_disable_data_inputs(self, action):
        if action not in ['enable', 'disable']:
            raise ProcessControlInternalException('Invalid action specified: %s' % action)

        svc = Service(port=getDefault('port'),
                      token=session['authtoken'],
                      app=em_constants.APP_NAME,
                      owner='nobody')
        for kind, name in NonMigrationDataInputsController.data_inputs_list:
            try:
                data_input = svc.inputs[name, kind]
                if action == 'enable':
                    logger.info('Enabling data input %s://%s...' % (kind, name))
                    data_input.enable()
                else:
                    logger.info('Disabling data input %s://%s...' % (kind, name))
                    data_input.disable()
            except KeyError:
                logger.info('Data input %s://%s not found, skipping...' % (kind, name))
                continue


class SavedsearchController(object):
    """
    SavedsearchController enable/disables savedsearches that belongs to SAI in order to prevent
    them from interfering with the migration process
    """

    def __init__(self):
        self.svc = Service(port=getDefault('port'),
                           token=session['authtoken'],
                           app=em_constants.APP_NAME,
                           owner='nobody')
        self.savedsearch_with_states = []
        self._prepare_savedsearches()
        self.checkpoint = MigrationProcessControlCheckpoint.get_or_create()

    def _prepare_savedsearches(self):
        for savedsearch in self.svc.saved_searches.iter(search='alert.managedBy=%s*' % em_constants.APP_NAME):
            state = 'disabled' if is_true(savedsearch['disabled']) else 'enabled'
            self.savedsearch_with_states.append((savedsearch, state))

    @retry(exceptions=[HTTPError])
    def enable(self):
        prev_disabled_savedsearches = self._get_previously_disabled_savedsearches()
        for savedsearch in prev_disabled_savedsearches:
            logger.info('Enabling savedsearch %s...' % savedsearch['name'])
            savedsearch.update(disabled=0)
        self.checkpoint.clear_savedsearches_checkpoint()

    def _get_previously_disabled_savedsearches(self):
        mutated_ss = []
        for savedsearch, state in self.savedsearch_with_states:
            savedsearch_by_name = self.checkpoint.get_mutated_savedsearch(savedsearch['name'])
            if savedsearch_by_name is not None and savedsearch_by_name['final_state'].get('disabled'):
                mutated_ss.append(savedsearch)
        return mutated_ss

    @retry(exceptions=[HTTPError])
    def disable(self):
        for savedsearch, state in self.savedsearch_with_states:
            if state == 'disabled':
                continue
            logger.info('Disabling savedsearch %s...' % savedsearch['name'])
            savedsearch.update(disabled=1)

            self.checkpoint.report_savedsearch_change(
                savedsearch['name'],
                initial_state={'disabled': False},
                final_state={'disabled': True}
            )
