import em_path_inject  # noqa

from em_abstract_custom_alert_action import AbstractCustomAlertAction
from logging_utils import log
from em_model_entity import EmEntity
import time

logger = log.getLogger()


class EmRetireEntitiesAlertAction(AbstractCustomAlertAction):
    def execute(self, results, payload):
        entity_to_retire_keys = [res['key'] for res in results]

        if len(entity_to_retire_keys):
            try:
                EmEntity.bulk_delete({'_key': entity_to_retire_keys})
                self.service.messages.create(
                    'successful-retirement-%s' % time.time(),
                    severity='info',
                    value='Successfully retired %s inactive entities.' % len(entity_to_retire_keys)
                )
            except Exception as e:
                logger.error('failed to retire entities - error: %s' % e)


instance = EmRetireEntitiesAlertAction()

if __name__ == '__main__':
    instance.run()
