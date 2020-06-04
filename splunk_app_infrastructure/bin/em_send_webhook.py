import em_path_inject  # noqa
from builtins import str
import json
import requests
from future.moves.urllib.parse import urlencode
from em_abstract_custom_alert_action import AbstractCustomAlertAction
from em_exceptions import WebhookCouldNotSendAlertException
from em_model_entity import EmEntity
from em_model_group import EMGroup
from logging_utils import log

logger = log.getLogger()

ALERT_SEVERITY = {
    'None': 'INFO',
    '1': 'INFO',
    '3': 'WARNING',
    '5': 'CRITICAL'
}

WORKSPACE_URL_TEMPLATE = '{base_url}/app/splunk_app_infrastructure/metrics_analysis?{encoded_params}'
ALERT_TYPE_GROUP = 'group'
ALERT_TYPE_ENTITY = 'entity'

# Fields that must have a value for alert to be sent
IMPORTANT_RESULT_FIELDS = ['current_value', 'managed_by_id', 'managed_by_type']
IMPORTANT_PAYLOAD_FIELDS = ['search_name', 'session_key']


class EMSendWebhookAlertAction(AbstractCustomAlertAction):
    # ALWAYS keep false only change from inside a testing program
    testing_mode_always_send_alerts = False
    ssContent = None

    def _make_action_url(self, result, payload):
        managed_by_id = result.get('managed_by_id')
        managed_by_type = result.get('managed_by_type')
        alert_title = payload.get('search_name')
        url_params = [
            (managed_by_type, managed_by_id),
            ('alert_name', alert_title),
            ('tab', 'ANALYSIS')
        ]
        custom_hostname = self.ssContent.get('hostname', None)
        url = WORKSPACE_URL_TEMPLATE.format(
            base_url=self._make_base_url(custom_hostname),
            encoded_params=urlencode(url_params)
        )
        return url

    def _convert_string_to_dict(self, input_str, separator_1, separator_2):
        output_dict = {}
        for key_value_pair in input_str.split(separator_1):
            key_value_pair_list = key_value_pair.split(separator_2)
            if len(key_value_pair_list) == 2:
                key = key_value_pair_list[0]
                value = key_value_pair_list[1].strip()
                output_dict[key] = value
        return output_dict

    def _metric_filters_string_to_dict_helper(self, metric_filters_str):
        """
        Helper to create metric filters dict
        """
        return self._convert_string_to_dict(metric_filters_str, separator_1='; ', separator_2=':')

    def _fixed_alert_data(self):
        """
        Data that will be present in all alerts
        """
        alert_data = {
            'version': '1',
            'type': 'alert'
        }
        return alert_data

    def _add_temporary_data_from_input_to_alert(self, alert_data, result, payload):
        """
        Adds data that will later be removed from alert
        """
        alert_data['entity_title'] = result.get('entity_title', '')
        alert_data['session_key'] = payload.get('session_key')
        return alert_data

    def _add_permanent_data_from_input_to_alert(self, alert_data, result, payload):
        """
        Adds data that will be in alert
        """
        settings = payload.get('configuration', {})
        alert_data['aggregation_method'] = result.get('aggregation_method', '').lower()
        alert_data['alert_severity'] = ALERT_SEVERITY[result.get('current_state', 'None')]
        alert_data['alert_title'] = payload.get('search_name')
        alert_data['managed_by_type'] = result.get('managed_by_type')
        alert_data['current_value'] = round(float(result.get('current_value', '-1')), 2)
        alert_data['managed_by_id'] = result.get('managed_by_id')
        alert_data['metric_name'] = result.get('metric_name', '')
        alert_data['state_change'] = result.get('state_change', 'no')
        if alert_data['state_change'] == 'no':
            alert_data['state_change'] = 'none'  # Rename no state change for readability
        alert_data['split_by'] = result.get('split_by', '')
        alert_data['split_by_value'] = result.get(alert_data['split_by'],
                                                  alert_data['entity_title'])
        alert_data['trigger_time'] = settings.get('trigger_time', '')
        alert_data['action_url'] = self._make_action_url(result, payload)
        alert_data['filters'] = {
            'metric_filters_inclusive':
            self._metric_filters_string_to_dict_helper(result.get('metric_filters_incl', '')),
            'metric_filters_exclusive':
            self._metric_filters_string_to_dict_helper(result.get('metric_filters_excl', ''))
        }
        return alert_data

    def _add_data_from_kvstore_to_alert(self, alert_data):
        """
        Adds data from the kvstore to the alert
        """
        managed_by_type = alert_data['managed_by_type']
        managed_by_id = alert_data['managed_by_id']
        entity_title = alert_data['entity_title']
        if managed_by_type == ALERT_TYPE_ENTITY:
            entity = EmEntity.get(managed_by_id)
            managed_by_value = entity_title
            dimensions = entity.dimensions
        else:
            group = EMGroup.get(managed_by_id)
            managed_by_value = group.title
            dimensions = group.filter.to_dict()

        alert_data['managed_by_value'] = managed_by_value
        alert_data['dimensions'] = dimensions
        return alert_data

    def _remove_temporary_data_from_alert(self, alert_data):
        """
        Removes any fields we do not want to send in the alert
        """
        alert_data.pop('entity_title')
        alert_data.pop('session_key')
        return alert_data

    def build_webhook_alert_payload(self, result, payload):
        """
        Constructs the entire alert
        """
        alert_data = self._fixed_alert_data()
        alert_data = self._add_temporary_data_from_input_to_alert(alert_data, result, payload)
        alert_data = self._add_permanent_data_from_input_to_alert(alert_data, result, payload)
        alert_data = self._add_data_from_kvstore_to_alert(alert_data)
        alert_data = self._remove_temporary_data_from_alert(alert_data)
        return alert_data

    def validate_required_message_fields(self, result, payload):
        """
        Raises an exception if important fields are not present in incoming result or payload
        """
        for important_field in IMPORTANT_RESULT_FIELDS:
            if important_field not in result:
                raise WebhookCouldNotSendAlertException('Field: %s is not present in result.' % important_field)
        for important_field in IMPORTANT_PAYLOAD_FIELDS:
            if important_field not in payload:
                raise WebhookCouldNotSendAlertException('Field: %s is not present in payload.' % important_field)

    def _create_request_url(self, payload):
        settings = payload.get('configuration')
        url = settings.get('webhook_url', '')
        return url

    def send_webhook_alert(self, result, payload):
        """
        Send an alert on the specified webhook
        """
        try:
            self.validate_required_message_fields(result, payload)
            url = self._create_request_url(payload)
            alert_payload = self.build_webhook_alert_payload(result, payload)
            # Attempt to send the message
            logger.debug('Calling url="%s" with payload="%s"' % (url, alert_payload))
            response = requests.post(url, json=alert_payload)
            if response.status_code < 200 or response.status_code >= 300:
                raise Exception('Response status code returned: %d' % response.status_code)
        except Exception as e:
            logger.error('Error when trying to send custom webhook alert: %s, Input result: %s, Input payload: %s'
                         % (str(e), json.dumps(result), json.dumps(payload)))

    def execute(self, results, payload):
        """
        Loop through the results and send webhook messages based on settings
        """
        if not results:
            return

        settings = payload.get('configuration')
        configuration_state_change_conditions = settings.get('webhook_when').split(',')

        self.ssContent = self.ssContent if self.ssContent else self.get_alert_action_setting('em_send_webhook')

        for result in results:
            state_change = result.get('state_change', 'no')
            if (
                state_change != 'no' and
                state_change in configuration_state_change_conditions and
                result.get('current_state') != 'None'
            ) or self.testing_mode_always_send_alerts:
                self.send_webhook_alert(result, payload)

        return results


instance = EMSendWebhookAlertAction()


if __name__ == '__main__':
    instance.run()
