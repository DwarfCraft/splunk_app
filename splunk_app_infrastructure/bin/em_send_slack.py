# coding=utf-8

import em_path_inject  # noqa
import datetime
import os
import json
import requests
from future.moves.urllib.parse import urlencode
from em_abstract_custom_alert_action import AbstractCustomAlertAction
from em_exceptions import SlackCouldNotSendAlertException
from logging_utils import log
from em_model_group import EMGroup

logger = log.getLogger()

ALERT_SEVERITY = {
    'None': 'INFO',
    '1': 'INFO',
    '3': 'WARNING',
    '5': 'CRITICAL'
}
# Colors used from packages/ui/configs/colors.js to match alert creation slider colors
SEVERITY_COLORS = {
    'None': '#7fd48b',  # SLIDER_GREEN
    '1': '#7fd48b',  # SLIDER_GREEN
    '3': '#F2B827',  # SLIDER_YELLOW
    '5': '#E86F65'  # SLIDER_RED
}

# Keep in mind this is not 100% markdown, it is Slack's flavor
# Slack uses single *s for bold text and <url|message> for hyperlinks
MESSAGE_MARKDOWN_TEMPLATE = '''\
*{alert_severity}: {alert_title}*
Alert Title: *{alert_title}*
Severity: *{alert_severity} {metric_name} : {current_value}*
State change: *{state_change}*
{aggregation_section}
{managed_by_type_cap} triggered this alert: *{managed_by_value}*
{managed_by_type_cap} id: *{managed_by_id}*
{group_definition_section}
{split_by_section}
{metric_filters_section}
Time triggered: *{trigger_time}*
'''
AGGREGATION_MARKDOWN_TEMPLATE = 'Aggregation: *{aggregation_method}*'
GROUP_DEFINITION_MARKDOWN_TEMPLATE = 'Group definition: *{group_filter}*'
SPLIT_BY_MARKDOWN_TEMPLATE = 'Split-by: *{split_by}={split_by_value}*'
METRIC_FILTERS_MARKDOWN_TEMPLATE = 'Metric filters ({section_type}): {metric_filters}'

WORKSPACE_URL_TEMPLATE = '{base_url}/app/splunk_app_infrastructure/metrics_analysis?{encoded_params}'
ALERT_LINK_TEXT = 'Investigate Now'
ALERT_TYPE_GROUP = 'group'
ALERT_TYPE_ENTITY = 'entity'

# Fields that must have a value for message to be sent
IMPORTANT_RESULT_FIELDS = ['current_value', 'managed_by_id', 'managed_by_type']
IMPORTANT_PAYLOAD_FIELDS = ['search_name', 'session_key']

# Image links are taken from Splunk's website
# in the future we might have to update them
AUTHOR_NAME = 'Splunk App for Infrastructure'
AUTHOR_LINK = 'https://splunkbase.splunk.com/app/3975/'
AUTHOR_ICON = 'https://www.splunk.com/content/dam/splunk2/images/icons/favicons/favicon.ico'
THUMB_URL = 'https://www.splunk.com/content/dam/splunk2/images/icons/favicons/mstile-150x150.png'


class EMSendSlackAlertAction(AbstractCustomAlertAction):
    # ALWAYS keep false only change from inside a testing program
    testing_mode_always_send_alerts = False
    ssContent = None

    def _make_investigate_now_url(self, result, payload):
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

    def make_slack_message_title(self, result, payload):
        """
        Title for the slack message
        """
        alert_url = self._make_investigate_now_url(result, payload)
        return '<{maw_url}|{alert_link_text}>'.format(maw_url=alert_url,
                                                      alert_link_text=ALERT_LINK_TEXT)

    def make_slack_message_color(self, result):
        """
        Picks severity color to use alongside the alert (Will appear next to alert, not behind)
        """
        return SEVERITY_COLORS[result.get('current_state')]

    def _get_trigger_time(self, payload):
        settings = payload.get('configuration')
        trigger_time = ''
        if settings:
            trigger_time = settings.get('trigger_time', '')
            if trigger_time:
                trigger_time = datetime.datetime.utcfromtimestamp(
                    float(settings.get('trigger_time'))).strftime('%Y-%m-%dT%H:%M:%SZ')
        return trigger_time

    def _initialize_message_template_values(self, result, payload):
        """
        Creates a dictionary whose values will be inserted into the template to
        create the message text. The aggregation, metric filters, group definition,
        and split by sections are not included
        """
        message_template_values = {}
        message_template_values['alert_title'] = payload.get('search_name')
        message_template_values['alert_severity'] = ALERT_SEVERITY[result.get('current_state', 'None')]
        message_template_values['metric_name'] = result.get('metric_name', '')
        message_template_values['current_value'] = round(float(result.get('current_value', '-1')), 2)
        message_template_values['state_change'] = result.get('state_change', 'no')
        message_template_values['managed_by_type'] = result.get('managed_by_type')
        message_template_values['managed_by_id'] = result.get('managed_by_id')
        message_template_values['session_key'] = payload.get('session_key')
        message_template_values['aggregation_method'] = result.get('aggregation_method', '').lower()
        message_template_values['metric_filters_incl'] = result.get('metric_filters_incl', '')
        message_template_values['metric_filters_excl'] = result.get('metric_filters_excl', '')
        message_template_values['split_by'] = result.get('split_by', 'None')
        message_template_values['entity_title'] = result.get('entity_title', '')
        message_template_values['trigger_time'] = self._get_trigger_time(payload)
        # Split-by identifier dimensions gives no split_by_value but adds entity_title
        message_template_values['split_by_value'] = result.get(message_template_values['split_by'],
                                                               message_template_values['entity_title'])
        # Capitalize first letter of managed_by_type since it will be the first word in a line
        message_template_values['managed_by_type_cap'] = message_template_values['managed_by_type'].capitalize()
        # Rename no state change for readability
        if message_template_values['state_change'] == 'no':
            message_template_values['state_change'] = 'none'
        return message_template_values

    def _metric_filters_section_helper(self, metric_filters_str):
        """
        Adds a newline and one tab indent for every metric filter in the metric filters section
        """
        rv = ''
        if metric_filters_str:
            for metric_filter_str in metric_filters_str.split('; '):
                rv += '\n\t*%s*' % metric_filter_str
        return rv

    def _add_aggregation_section(self, message_template_values):
        """
        Adds the aggregation section to the message template value dict
        """
        aggregation_method = message_template_values['aggregation_method']
        aggregation_section = AGGREGATION_MARKDOWN_TEMPLATE.format(
            aggregation_method=aggregation_method)
        message_template_values['aggregation_section'] = aggregation_section
        return message_template_values

    def _add_group_definition_section(self, message_template_values):
        """
        Adds the group definition section to the message template value dict
        """
        managed_by_type = message_template_values['managed_by_type']
        managed_by_id = message_template_values['managed_by_id']
        entity_title = message_template_values['entity_title']
        if managed_by_type == ALERT_TYPE_ENTITY:
            managed_by_value = entity_title
            group_definition_section = ''
        else:
            group = EMGroup.get(managed_by_id)
            group_filter = group.filter.to_str().replace(',', ', ')
            managed_by_value = group.title

            group_definition_section = GROUP_DEFINITION_MARKDOWN_TEMPLATE.format(group_filter=group_filter)
        message_template_values['managed_by_value'] = managed_by_value
        message_template_values['group_definition_section'] = group_definition_section
        return message_template_values

    def _add_split_by_section(self, message_template_values):
        """
        Adds the split by section to the message template value dict
        """
        split_by = message_template_values['split_by']
        split_by_value = message_template_values['split_by_value']
        if (split_by != 'None'):
            split_by_section = SPLIT_BY_MARKDOWN_TEMPLATE.format(split_by=split_by,
                                                                 split_by_value=split_by_value)
        else:
            split_by_section = ''
        message_template_values['split_by_section'] = split_by_section
        return message_template_values

    def _add_metric_filters_section(self, message_template_values):
        """
        Adds the metric filters section to the message template value dict
        """
        metric_filters_incl = message_template_values['metric_filters_incl']
        metric_filters_excl = message_template_values['metric_filters_excl']
        metric_filters_section = ''
        if (metric_filters_incl):
            metric_filters_section += METRIC_FILTERS_MARKDOWN_TEMPLATE.format(
                section_type='inclusive',
                metric_filters=self._metric_filters_section_helper(metric_filters_incl),
            )
        if (metric_filters_excl):
            if (metric_filters_section != ''):
                metric_filters_section += '\n'
            metric_filters_section += METRIC_FILTERS_MARKDOWN_TEMPLATE.format(
                section_type='exclusive',
                metric_filters=self._metric_filters_section_helper(metric_filters_excl),
            )
        message_template_values['metric_filters_section'] = metric_filters_section
        return message_template_values

    def make_slack_message_text(self, result, payload):
        """
        Constructs the slack message's text. The result is a string with
        the values from the results formatted in slack's version of markdown
        """
        # Construct the template value dictionary
        message_template_values = self._initialize_message_template_values(result, payload)
        message_template_values = self._add_aggregation_section(message_template_values)
        message_template_values = self._add_group_definition_section(message_template_values)
        message_template_values = self._add_split_by_section(message_template_values)
        message_template_values = self._add_metric_filters_section(message_template_values)

        # Format template using values from the dictionary, and remove any empty lines
        text = MESSAGE_MARKDOWN_TEMPLATE.format(**message_template_values)
        text = os.linesep.join([line for line in text.splitlines() if line])
        return text

    def build_slack_message_payload(self, result, payload):
        """
        Constructs message payload. This includes the icon image, username,
        the alert message itself and tells slack that it is markdown formatted
        """
        message_title = self.make_slack_message_title(result, payload)
        message_text = self.make_slack_message_text(result, payload)
        color = self.make_slack_message_color(result)

        # Slack API message attachments documentation: https://api.slack.com/docs/message-attachments
        params = {}
        params['attachments'] = [{
            'author_name': AUTHOR_NAME,
            'author_link': AUTHOR_LINK,
            'author_icon': AUTHOR_ICON,
            'title': message_title,
            'text': message_text,
            'fallback': message_title,
            'color': color,
            'mrkdwn_in': ['text'],
            'thumb_url': THUMB_URL
        }]

        return params

    def validate_required_message_fields(self, result, payload):
        """
        Raises an exception if important fields are not present in incoming result or payload
        """
        for important_field in IMPORTANT_RESULT_FIELDS:
            if important_field not in result:
                raise SlackCouldNotSendAlertException('Field: %s is not present in result.' % important_field)
        for important_field in IMPORTANT_PAYLOAD_FIELDS:
            if important_field not in payload:
                raise SlackCouldNotSendAlertException('Field: %s is not present in payload.' % important_field)

    def _create_request_url(self, payload):
        settings = payload.get('configuration')
        url = settings.get('webhook_url', '')
        return url

    def send_slack_message(self, result, payload):
        """
        Send a slack message on the specified webhook
        """
        try:
            self.validate_required_message_fields(result, payload)

            url = self._create_request_url(payload)

            message_payload = json.dumps(self.build_slack_message_payload(result, payload))

            # Attempt to send the message
            logger.debug('Calling url="%s" with payload="%s"' % (url, message_payload))
            response = requests.post(url, data=message_payload)
            if response.status_code < 200 or response.status_code >= 300:
                raise Exception('Response status code returned: %d' % response.status_code)
        except Exception as e:
            logger.error('Error when trying to send slack webhook alert: %s, Input result: %s, Input payload: %s'
                         % (e.message, json.dumps(result), json.dumps(payload)))

    def execute(self, results, payload):
        """
        Loop through the results and send slack messages based on settings.
        """
        if not results:
            return

        settings = payload.get('configuration')
        configuration_state_change_conditions = settings.get('slack_when').split(',')

        self.ssContent = self.ssContent if self.ssContent else self.get_alert_action_setting('em_send_slack')

        for result in results:
            state_change = result.get('state_change', 'no')
            if (
                state_change != 'no' and
                state_change in configuration_state_change_conditions and
                result.get('current_state') != 'None'
            ) or self.testing_mode_always_send_alerts:
                self.send_slack_message(result, payload)

        return results


instance = EMSendSlackAlertAction()


if __name__ == '__main__':
    instance.run()
