import em_path_inject  # noqa

from splunk import getDefault
from splunklib.modularinput.argument import Argument
from splunklib.client import Service
from solnlib.utils import retry
from logging_utils import log
from rest_handler.session import session, UnauthenticatedException
from modinput_wrapper.base_modularinput import BaseModularInput
import sys
from future.moves.urllib.error import HTTPError

import em_constants
import em_common
from em_model_entity_class import EntityClass, EntityClassInternalException
from em_subscription_utils import has_collector_subscription

logger = log.getLogger()


class EntityClassManager(BaseModularInput):
    """
    `EntityClassManager` manages overall process of reading and transforming of entity classes
    """

    app = em_constants.APP_NAME
    name = "em_entity_class_manager"
    title = "Entity Class Manager"
    description = "Entity class manager modular input"
    use_external_validation = False
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    use_single_instance = True

    def __init__(self):
        super(EntityClassManager, self).__init__()

    def extra_arguments(self):
        return [
            {
                'name': 'log_level',
                'title': 'Log level',
                'description': 'Log level for entity class manager modular input, default to WARNING',
                'required_on_create': False,
                'data_type': Argument.data_type_string
            }
        ]

    def do_additional_setup(self):
        log_level = self.inputs.get('job', {}).get('log_level', 'WARNING')
        logger.setLevel(log.parse_log_level(log_level))
        self.service = Service(
            port=getDefault('port'),
            token=session['authtoken'],
            app=em_constants.APP_NAME,
            owner='nobody',
        )

    def do_execute(self):
        """
        Implements the `do_execute` method of parent class. It transforms entity classes into savedsearches
        """
        logger.info('Start initializing entity class savedsearches...')
        entity_classes = self.load_entity_classes()
        cur_entity_class_keys = set(ec.key for ec in entity_classes)
        subscribed_entity_class_keys = []
        for entity_class_key in cur_entity_class_keys:
            if has_collector_subscription(
                    server_uri=em_common.get_server_uri(),
                    session_key=session['authtoken'],
                    collector_name=entity_class_key):
                subscribed_entity_class_keys.append(entity_class_key)
        ec_savedsearch_managed_by_prefix = '{}:entity_class:'.format(em_constants.APP_NAME)
        # clean up old savedsearches
        logger.info('Cleaning up obsolete entity class savedsearches...')
        for ss in self.service.saved_searches:
            if ss['alert.managedBy'] and ss['alert.managedBy'].startswith(ec_savedsearch_managed_by_prefix):
                ss_entity_class_key = ss['alert.managedBy'][len(ec_savedsearch_managed_by_prefix):]
                if ss_entity_class_key not in subscribed_entity_class_keys:
                    self.service.saved_searches.delete(ss['name'])
                    logger.info('Deleted savedsearch %s' % ss['name'])

        # upsert new/updated savedsearches
        logger.info('Upserting new/updated entity class savedsearches...')
        for ec in entity_classes:
            if ec.key not in subscribed_entity_class_keys:
                continue
            logger.debug('entity class: %s' % ec.__dict__)
            try:
                ec.upsert_savedsearch()
                logger.info('Upserted savedsearch for entity class %s' % ec.key)
            except EntityClassInternalException:
                continue
            except UnauthenticatedException as e:
                logger.error(e)

    @retry(retries=3, exceptions=[HTTPError])
    def load_entity_classes(self):
        entity_classes = EntityClass.load()
        return entity_classes


if __name__ == '__main__':
    exit_code = EntityClassManager().execute()
    sys.exit(exit_code)
