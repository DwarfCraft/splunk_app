import em_path_inject # noqa

import time
from hashlib import sha256

import em_common
import em_constants
from em_model_alert import EMAlert
from em_model_entity import EmEntity
from em_model_entity_class import EntityClass
from em_search_manager import EMSearchManager
from service_manager.splunkd.kvstore import KVStoreManager
from service_manager.splunkd.savedsearch import SavedSearchManager
from utils import to_bytes
from .base_migration_handler import BaseMigrationHandler


class StaticEntityToDynamicEntity(BaseMigrationHandler):

    description = 'Convert orginal SAI entities to dynamic entities and update alerts to ' + \
                  'link to the freshly-converted dynamic entities'

    def __init__(self, logger, session_key):
        super(StaticEntityToDynamicEntity, self).__init__(logger, session_key)

        server_uri = em_common.get_server_uri()
        self.search_manager = EMSearchManager(
            server_uri=server_uri,
            session_key=self.session_key,
            app=em_constants.APP_NAME,
        )
        self.saved_search_manager = SavedSearchManager(
            session_key=self.session_key,
            server_uri=server_uri,
            app=em_constants.APP_NAME,
        )
        self.static_entity_store = KVStoreManager(
            collection='em_entities',
            server_uri=server_uri,
            session_key=self.session_key,
            app=em_constants.APP_NAME,
        )

        self.entity_classes = {ec.key: ec for ec in EntityClass.load()}
        self.new_entities = []
        self.updated_alerts = {}
        self.entity_key_mapping = {}
        self.existing_dynamic_entities = set([e.key for e in EmEntity.load(0, 0, '', 'asc')])

    def load_sai_alerts(self):
        alerts = []
        saved_searches = self.saved_search_manager.load()['entry']
        for saved_search in saved_searches:
            # Filter for saved searches that represent SAI alerts
            if (not saved_search['content']['alert.managedBy'].startswith(
                    'splunk_app_infrastructure:')
                    or saved_search['content']['alert.managedBy'].startswith(
                    'splunk_app_infrastructure:entity_class:')):
                continue
            alerts.append(saved_search)
        return alerts

    def prepare_dynamic_entities_from_static_entities(self, static_entities):
        self.logger.info(
            'Preparing DE entities from static entities, number of entities to migrate: %d' % len(static_entities)
        )
        for entity in static_entities:
            collector_name = entity['collectors'][0]['name']
            entity_class = self.entity_classes[collector_name]
            unhashed_key_parts = [entity['dimensions'][identifier_dimension] for identifier_dimension
                                  in entity_class.identifier_dimensions]
            unhashed_key_parts.append(collector_name)
            entity_key = sha256(to_bytes(':'.join(unhashed_key_parts))).hexdigest()

            now = int(time.time())

            new_entity = EmEntity(
                key=entity_key,
                title=entity['title'],
                entity_class=collector_name,
                mod_time=now,
                expiry_time=now + entity_class.monitoring_window,
                identifier_dimension_names=entity_class.identifier_dimensions,
                dimensions=entity['dimensions'],
            )
            self.new_entities.append(new_entity._raw())
            self.entity_key_mapping[entity['_key']] = new_entity.key

    def prepare_dynamic_entity_alerts(self, old_alerts):
        self.logger.info('Preparing alerts, number of alerts to migrate: %d' % len(old_alerts))
        # Update alerts to account for different location, format of dynamic entities
        for alert in old_alerts:
            alert_content = {k: v for k, v in alert['content'].items() if k in
                             ['alert.managedBy', 'search']}
            try:
                managed_by_type = EMAlert.parse_managed_by_type(alert_content['search'])
                metric_spl = EMAlert.parse_metric_spl(alert_content['search'])
                threshold = EMAlert.parse_threshold_params(alert_content['search'])
                metric_filters = EMAlert.parse_metric_filters(alert_content['search'])
            except Exception as e:
                self.error_count += 1
                self.logger.error('[%s] Alert parsing error with %s: %s' %
                                  (self.name, alert['name'], e))
                continue

            alert_content['search'] = EMAlert(
                name=alert['name'],
                managed_by=alert_content['alert.managedBy'],
                managed_by_type=managed_by_type,
                metric_spl=metric_spl,
                threshold=threshold,
                # We're not mocking the actions (because we're not updating them), so don't save this alert via
                # its normal method.
                actions=[],
                metric_filters=metric_filters,
            ).convert_spl()

            # Update entity alert
            if managed_by_type == 'entity':
                static_entity_id = alert_content['alert.managedBy'][len('splunk_app_infrastructure:'):]
                try:
                    dynamic_entity_id = self.entity_key_mapping[static_entity_id]
                except KeyError:
                    # This alert has somehow already been processed
                    if static_entity_id in self.existing_dynamic_entities:
                        continue
                    self.error_count += 1
                    self.logger.error('[%s] Alert %s references a missing entity (%s)'
                                      % (self.name, alert['name'], static_entity_id))
                    continue

                alert_content['search'] = alert_content['search'].replace(
                    static_entity_id, dynamic_entity_id)
                alert_content['alert.managedBy'] = alert_content['alert.managedBy'].replace(
                    static_entity_id, dynamic_entity_id)

            self.updated_alerts[alert['name']] = alert_content

    def _calculate_changes(self):
        static_entities = self.static_entity_store.load_all()
        self.prepare_dynamic_entities_from_static_entities(static_entities)

        alerts = self.load_sai_alerts()
        self.prepare_dynamic_entity_alerts(alerts)

    def _apply_changes(self):
        if self.new_entities:
            EmEntity.storage_bulk_save(self.new_entities)
        for k, v in self.updated_alerts.items():
            self.saved_search_manager.update(k, v)
