# Copyright 2018 Splunk Inc. All rights reserved.
# Environment configuration
import em_path_inject  # noqa
import json
import re
import sys

from builtins import range

import em_common
import em_utils
import splunk.rest
from em_model_entity import EmEntity
from em_constants import APP_NAME, DEFAULT_BATCH_SIZE, ENTITY_CLASS_TO_ENTITY_TYPE_IDS
from em_exceptions import ArgValidationException
from itoamodels import Entity
from logging_utils import log
from modinput_wrapper.base_modularinput import BaseModularInput
from rest_handler.session import session
from solnlib import conf_manager
from solnlib.utils import is_true
from splunk import getDefault
from splunklib.client import Service
from splunklib.modularinput.argument import Argument
from utils.i18n_py23 import _

# Migration inputs
ENTITY_MIGRATION_INPUT = "em_entity_migration://job"
# Default publish url for message bus
DEFAULT_PUBLISH_URL = "/servicesNS/nobody/SA-ITOA/itoa_entity_exchange/publish"
# from itsi_const.py
ITSI_ENTITY_INTERNAL_KEYWORD = ['title', '_key', 'services', 'description', 'informational', 'identifier', 'create_by',
                                'create_time', 'create_source', 'mod_by', 'mod_time', 'mod_source', 'object_type',
                                '_type', '_owner', '_user', 'identifying_name', '_itsi_identifier_lookups',
                                'entity_type_ids']

try:
    basestring
except NameError:
    basestring = str

logger = log.getLogger()


class EMEntityMigration(BaseModularInput):
    """
    Entity Migration modular input
    This ModInput is responsible for convert em_entity to a common itoa model
    then post to message bus specified in publish_url
    """

    app = APP_NAME
    name = 'em_entity_migration'
    title = 'Splunk App for Infrastructure - Entity Migration'
    description = 'Entity Migration with conversion from SAI to ITSI entities'
    use_external_validation = False
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    regex_entity_title_invalid_chars = re.compile(r'[="\']+')
    regex_entity_dims_invalid_chars = re.compile(r'^\$|[=.,"\']+')

    def __init__(self):
        """
        Init modular input for entity migration
        """
        super(EMEntityMigration, self).__init__()
        self.splunkd_messages_service = None

    def extra_arguments(self):
        return [
            {
                'name': 'log_level',
                'title': 'Log level',
                'description': 'Log level, default to WARNING',
                'required_on_create': False,
                'data_type': Argument.data_type_string
            },
            {
                'name': 'publish_url',
                'title': 'Publish URL',
                'description': 'The publish URL of the message bus',
                'required_on_create': True,
                'data_type': Argument.data_type_string
            },
        ]

    def do_additional_setup(self):
        # set log level
        log_level = self.inputs.get('job', {}).get('log_level', 'WARNING')
        logger.setLevel(log.parse_log_level(log_level))
        # set up message service
        self.splunkd_messages_service = Service(port=getDefault('port'),
                                                token=session['authtoken'],
                                                app=APP_NAME,
                                                owner='nobody').messages
        # set up conf file manager
        self.inputs_conf = conf_manager.ConfManager(session['authtoken'], APP_NAME,
                                                    port=getDefault('port')).get_conf('inputs')

    def do_execute(self):
        """
        Main loop function, run every "interval" seconds
        :return: void
        """
        if self.is_migration_job_disabled():
            return
        try:
            if not em_common.modular_input_should_run(session['authtoken']):
                logger.info("em_entity_migration modinput will not run on non-captain node. exiting...")
                return

            # use hard coded url if not found
            publish_url = self.inputs['job'].get('publish_url', DEFAULT_PUBLISH_URL)
            logger.debug('publish_url set to %s' % publish_url)

            if em_common.is_url_valid(session['authtoken'], publish_url):
                itoa_entities = self.prepare_itoa_entities()
                if not len(itoa_entities):
                    logger.info('There are no SAI entities for migration.')
                    return
                self.publish_to_mbus(itoa_entities, publish_url)
                logger.info('%s entities successfully published to message bus' % len(itoa_entities))
            else:
                self.inputs_conf.update(ENTITY_MIGRATION_INPUT, {'disabled': 1})
                # NOTE: the _reload endpoint never worked, a hard restart is required to actualy stop this script
                # from running
                self.inputs_conf.reload()
                logger.info('disabled and reloaded entity migration input stanza')
        except Exception as e:
            logger.error('Failed to run entity migration modular input -- Error: %s' % e)
            link_to_error = em_utils.get_check_internal_log_message()
            self.splunkd_messages_service.create(
                'entity-migration-failure',
                severity='warn',
                value='Failed to migrate entities to ITSI. ' + link_to_error
            )

    def is_migration_job_disabled(self):
        # check if the job stanza exists
        job_stanza = self.inputs.get('job')
        if job_stanza is None:
            logger.warning('No valid job stanza found. Exiting...')
            return True
        conf_job_stanza = self.inputs_conf.get(ENTITY_MIGRATION_INPUT)
        if is_true(conf_job_stanza['disabled']):
            logger.info('job stanza is disabled. Exiting...')
            return True
        return False

    def prepare_itoa_entities(self):
        """
        Check if kvstore is ready, if not simply exit

        If ready, load all SAI entities and convert them into ITOA entities
        :return: itoa_entities
        """
        try:
            em_common.check_kvstore_readiness(session['authtoken'])
        except em_common.KVStoreNotReadyException as e:
            logger.error('Migrate SAI entities to ITSI failed because KVStore is not ready - Error: %s' % e)
            sys.exit(1)

        all_entities = EmEntity.load(0, 0, '', 'asc')
        return self._convert_to_itoa(all_entities)

    def _convert_to_itoa(self, sai_entities):
        """
        convert entities to itoa

        :return: List of entities in KVSTore
        """
        itoa_entities = []
        for sai_entity in sai_entities:
            if self._should_publish_entity_to_itsi(sai_entity):
                filtered_dims = self._filter_invalid_dimensions_of_entity(sai_entity.dimensions)
                aliases = {k: filtered_dims[k] for k in sai_entity.identifier_dimension_names}
                # entity_type_ids is a list of strings
                entity_type_ids = []
                if sai_entity.entity_class in ENTITY_CLASS_TO_ENTITY_TYPE_IDS:
                    entity_type_ids = [ENTITY_CLASS_TO_ENTITY_TYPE_IDS[sai_entity.entity_class]]
                ex = Entity({
                    'unique_id': sai_entity.key,
                    'aliases': aliases,
                    'title': sai_entity.title,
                    'informational': filtered_dims,
                    'entity_type_ids': entity_type_ids,
                    'creation_time': 0,
                    'updated_time': sai_entity.mod_time,
                })
                itoa_entities.append(ex)

        return itoa_entities

    def _should_publish_entity_to_itsi(self, entity):
        """
        if identifier dimensions contains invalid characters then don't migrate that entity at all
        because of the close association between entity _key and identifier dimensions and how alias
        is used to attribute KPIs and other calculation results to specific entity
        """
        # only publish active entities to itsi
        if entity.status != EmEntity.ACTIVE:
            return False

        # validate title (validation rules from itsi_entity.py)
        if ((not entity.title.strip()) or
                re.search(self.regex_entity_title_invalid_chars, entity.title)):
            logger.warning(
                'SAI entity %s will not be published to message bus because '
                'its title contains invalid characters. '
                'Invalid characters are single quotes (\'), double quotes (") and equal sign (=)' % entity.title
            )
            return False

        # validate dims (validation rules from itsi_entity.py)
        for dim in entity.identifier_dimension_names:
            if not self._is_dimension_name_valid_for_itsi(dim):
                logger.warning(
                    'SAI entity %s will not be published to message bus because '
                    'its identifier dimension "%s" contains invalid characters. '
                    'Invalid characters are single quotes (\'), double quotes ("), $ (as first character), '
                    'equal sign (=), period (.), and commas (,)' % (entity.title, dim)
                )
                return False
        return True

    def _filter_invalid_dimensions_of_entity(self, dimensions):
        """
        Filter out invalid dimensions of the given dimensions dict. This method
        does not modify the input dict.

        :param dimensions: a dimensions dict
        :return a new dimensions dict with invalid dim filtered out
        """
        dims = {}
        for dim_name in dimensions:
            if self._is_dimension_name_valid_for_itsi(dim_name):
                dims.update({dim_name: dimensions[dim_name]})
        return dims

    def _is_dimension_name_valid_for_itsi(self, dimension_name):
        if re.search(self.regex_entity_dims_invalid_chars, dimension_name):
            return False

        if dimension_name in ITSI_ENTITY_INTERNAL_KEYWORD:
            return False

        return True

    def publish_to_mbus(self, itoa_entities, url):
        entities_list = [entity.raw_data() for entity in itoa_entities]
        self._batch_save_to_mbus(data=entities_list, url=url)

    def _batch_save_to_mbus(self, data, url):
        """
        Perform multiple save operations in a batch
        """
        if not data:
            raise ArgValidationException(_('Batch saving failed: Batch is empty.'))

        batches = (data[x:x + DEFAULT_BATCH_SIZE]
                   for x in range(0, len(data), DEFAULT_BATCH_SIZE))
        for batch in batches:
            try:
                payload = {
                    "publisher": "Splunk App for Infrastructure",
                    "entities": batch
                }
                response, content = splunk.rest.simpleRequest(
                    url,
                    method='POST',
                    sessionKey=session['authtoken'],
                    jsonargs=json.dumps(payload)
                )
                if response.status != 200:
                    logger.error(
                        "Failed to publish entities to message bus -- status:%s content:%s" %
                        (response.status, content)
                    )
            except Exception as e:
                logger.error(e)
                raise e


if __name__ == '__main__':
    exitcode = EMEntityMigration().execute()
    sys.exit(exitcode)
