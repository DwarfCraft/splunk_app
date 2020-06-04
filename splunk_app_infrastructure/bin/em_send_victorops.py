import em_path_inject  # noqa
from builtins import str
from em_abstract_custom_alert_action import AbstractCustomAlertAction
from em_exceptions import VictorOpsCouldNotSendAlertException, VictorOpsNotExistException
from em_model_victorops import EMVictorOps, SPLUNK_ALERT_CODE_TO_VICTOROPS_INCIDENT_LEVEL
from em_model_group import EMGroup
from em_model_entity import EmEntity
from logging_utils import log
from future.moves.urllib.parse import urlencode

from utils.i18n_py23 import _

logger = log.getLogger()

WORKSPACE_URL_BODY = '%s/app/splunk_app_infrastructure/metrics_analysis?%s'
ALERT_TYPE_GROUP = 'group'
ALERT_TYPE_ENTITY = 'entity'


class EMSendVictorOpsAlertAction(AbstractCustomAlertAction):
    ssContent = None

    def _fetch_vo_setting(self, session_key):
        EMVictorOps.setup(session_key)
        vo_list = EMVictorOps.load()
        if len(vo_list):
            return vo_list[0]
        raise VictorOpsNotExistException(_('VictorOps setting does not exist'))

    def make_incident_from_alert(self, result, session_key):

        incident = {}
        # name of alert triggered
        alert_name = result['ss_id']
        incident['Alert Name'] = alert_name
        # metric being alerted on
        metric_name = result['metric_name']
        incident['Metric Name'] = metric_name
        # State of metric at time of alert. If metric is info, warn, or critical. This is same as 'message_type'
        alert_state_and_incident_level = SPLUNK_ALERT_CODE_TO_VICTOROPS_INCIDENT_LEVEL[result['current_state']]
        incident['Metric State'] = alert_state_and_incident_level
        # if metric improved or degraded
        state_change = result['state_change']
        incident['Metric State Change'] = state_change

        # value of metric at time of alert
        metric_value = str(round(float(result['current_value']), 1))
        incident['Metric Value'] = metric_value

        # Now setting entity and group specific information
        # Fetching some variables which are necessary in multiple places later
        managed_by_id = result['managed_by_id']
        managed_by_type = result.get('managed_by_type', '')
        entity_title = result.get('entity_title', '')
        aggregation = result.get('aggregation_method', '').lower()
        metric_filters_incl = result.get('metric_filters_incl', '')
        metric_filters_excl = result.get('metric_filters_excl', '')
        split_by = result.get('split_by', '')
        split_by_value = result.get(split_by, '')
        # Split-by identifier dimensions gives no split_by_value but adds entity_title
        if (split_by and not split_by_value):
            split_by_value = entity_title

        if (metric_filters_incl):
            incident['Metric Filters (Inclusive)'] = metric_filters_incl
        if (metric_filters_excl):
            incident['Metric Filters (Exclusive)'] = metric_filters_excl

        # If alert is coming from GROUP...
        if result['managed_by_type'] == ALERT_TYPE_GROUP:
            group = EMGroup.get(managed_by_id)
            filter_dimensions_dict = group.filter.to_dict()
            title = group.title

            filter_dimensions_formatted = EMSendVictorOpsAlertAction._format_filter_dimensions(filter_dimensions_dict)
            workspace_link = self._make_workspace_url(ALERT_TYPE_GROUP, managed_by_id, alert_name)
            incident['Group Triggering Alert'] = title
            incident['Dimensions on Originating Group'] = filter_dimensions_formatted
            incident['Link to Alert Workspace'] = workspace_link
        else:
            # If alert is coming from ENTITY...
            entity = EmEntity.get(managed_by_id)
            title = entity_title

            filter_dimensions_formatted = EMSendVictorOpsAlertAction._format_filter_dimensions(entity.dimensions)
            workspace_link = self._make_workspace_url(ALERT_TYPE_ENTITY, managed_by_id, alert_name)
            incident['Host Triggering Alert'] = entity_title
            incident['Dimensions on Originating Host'] = filter_dimensions_formatted
            incident['Link to Alert Workspace'] = workspace_link

        # Lastly, setting victorops-specific info
        # message_type tells VO whether incident is info, warn, or critical
        incident['message_type'] = alert_state_and_incident_level
        # entity_id is incident's uuid. It lets you update the incident. It has nothing to do with SII entity concept.
        incident['entity_id'] = '%s_%s' % (managed_by_id, metric_name)
        # VO uses message to populate emails, service now tickets, slack etc
        # Group (or entity) split-by alert
        if (split_by != 'None'):
            split_by_clause = (
                ' ({aggregation}) on {managed_by_type}: {title}, {split_by}: '
                '{split_by_value}'
                ).format(
                    managed_by_type=managed_by_type,
                    title=title,
                    split_by=split_by,
                    split_by_value=split_by_value,
                    aggregation=aggregation
                )
        # Entity or group aggregation alert
        else:
            split_by_clause = (
                ' ({aggregation}) on {managed_by_type}: {title}'
                ).format(
                    managed_by_type=managed_by_type,
                    title=title,
                    aggregation=aggregation
                )

        message = '{metric_name} {state_change}s to {metric_value}{split_by_clause}'.format(
            metric_name=metric_name,
            state_change=state_change,
            metric_value=metric_value,
            split_by_clause=split_by_clause
        )
        incident['state_message'] = message
        incident['entity_display_name'] = message
        return incident

    def _make_workspace_url(self, group_or_entity_label, group_or_entity_id, alert_name):
        id_and_alert_params = {
            group_or_entity_label: group_or_entity_id,
            'alert_name': alert_name,
            'tab': 'ANALYSIS'
        }
        id_and_alert_encoded = urlencode(id_and_alert_params)
        custom_hostname = self.ssContent.get('hostname', None)
        workspace_url = WORKSPACE_URL_BODY % (self._make_base_url(custom_hostname), id_and_alert_encoded)
        return workspace_url

    @staticmethod
    def _format_filter_dimensions(filter_dimensions_dict):
        formatted_strings = []
        for key, value in sorted(filter_dimensions_dict.items()):
            formatted_strings.append('%s: %s' % (key, ', '.join(value)))

        return '; '.join(formatted_strings)

    def execute(self, results, payload):
        try:
            configuration_state_change_conditions = payload['configuration']['victorops_when'].split(',')
            session_key = payload['session_key']
            vo = self._fetch_vo_setting(session_key)

            self.ssContent = self.ssContent if self.ssContent else self.get_alert_action_setting('em_send_victorops')

            for result in results:
                state_change = result['state_change']
                if state_change in configuration_state_change_conditions:
                    incident = self.make_incident_from_alert(result, session_key)
                    vo.send_incident(incident)
        except Exception as e:
            logger.error('Failed to send alert to VictorOps: %s', e.message)
            raise VictorOpsCouldNotSendAlertException(e.message)


instance = EMSendVictorOpsAlertAction()


if __name__ == '__main__':
    instance.run()
