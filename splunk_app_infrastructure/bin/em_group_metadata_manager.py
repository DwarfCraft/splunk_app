# Copyright 2019 Splunk Inc. All rights reserved.
# Environment configuration
import em_path_inject  # noqa
# Standard Python Libraries
import sys
from collections import Counter
# Custom Libraries
from splunklib.modularinput.argument import Argument
from modinput_wrapper.base_modularinput import BaseModularInput
from rest_handler.session import session
from service_manager.splunkd.kvstore import KVStoreManager
from em_model_entity import EmEntity
from em_model_group import EMGroup
import em_constants
import em_common
from logging_utils.instrument import Instrument
from logging_utils import log

logger = log.getLogger()


class EmGroupMetadataManager(BaseModularInput):
    """
    `EmGroupMetadataManager` manages overall process of reading and transforming of group classes
    """

    app = em_constants.APP_NAME
    name = "em_group_metadata_manager"
    title = "Group Metadata Manager"
    description = "Group metadata manager modular input"
    use_external_validation = False
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    use_single_instance = True

    def __init__(self):
        super(EmGroupMetadataManager, self).__init__()

    def extra_arguments(self):
        return [
            {
                'name': 'log_level',
                'title': 'Log level',
                'description': 'Log level, default to WARNING',
                'required_on_create': False,
                'data_type': Argument.data_type_string
            }
        ]

    def do_additional_setup(self):
        self.session_key = session['authtoken']
        log_level = self.inputs.get('job').get('log_level', 'WARNING')
        logger.setLevel(log.parse_log_level(log_level))
        self.group_store = KVStoreManager(
            em_constants.STORE_GROUPS,
            em_common.get_server_uri(),
            self.session_key,
            app=em_constants.APP_NAME)

    @Instrument(step='update group membership', process='group_metadata_manager')
    def update_group_membership(self):
        logger.info('Starting group membership update...')
        # reload all the entities after discovery are done
        all_groups = EMGroup.load(0, 0, '', 'asc')
        all_entities = EmEntity.load(0, 0, '', 'asc')
        data_list = []
        # go through each group and update entities count
        for group in all_groups:
            entities = [en for en in all_entities if group.check_entity_membership(en)]
            entity_status_breakdown = Counter(en.status for en in entities)
            group.entities_count = len(entities)
            group.active_entities_count = entity_status_breakdown.get(EmEntity.ACTIVE, 0)
            group.inactive_entities_count = entity_status_breakdown.get(EmEntity.INACTIVE, 0)
            logger.info('group "%s" metadata - active: %s, inactive: %s, count: %s' % (
                group.title, group.active_entities_count, group.inactive_entities_count, len(entities)
            ))
            data_list.append(group.get_raw_data())

        self.group_store.batch_save(data_list)
        logger.info('Finished group membership update...')

    @Instrument(step='modinput_entry', process='group_metadata_manager')
    def do_execute(self):
        """
        Main loop function, run every "interval" seconds
        :return: void
        """
        try:
            if not em_common.modular_input_should_run(session['authtoken'], logger=logger):
                logger.info("em_group_metadata_manager modinput will not run on this non-captain node.")
                return
            self.update_group_membership()
        except Exception as e:
            logger.error('Failed to execute group metadata manager modular input -- Error: %s' % e)


if __name__ == '__main__':
    exitcode = EmGroupMetadataManager().execute()
    sys.exit(exitcode)
