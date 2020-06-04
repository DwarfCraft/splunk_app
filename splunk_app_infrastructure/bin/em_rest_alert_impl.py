import em_path_inject  # noqa
from builtins import object
import http.client

from logging_utils import log
from rest_handler.exception import BaseRestException
from service_manager.splunkd.savedsearch import SavedSearchManager
from em_model_threshold import EMThreshold
from em_model_alert_action import EMVictorOpsAlertAction, EMEmailAlertAction, EMSlackAlertAction, \
    EMWriteAlertAction, EMWebhookAlertAction
from em_model_alert import EMAlert, AlertArgValidationException, AlertInternalException
import em_constants
import em_common
from utils.i18n_py23 import _


class AlertNotFoundException(BaseRestException):

    def __init__(self, message):
        super(AlertNotFoundException, self).__init__(http.client.NOT_FOUND, message)


class AlertAlreadyExistsException(BaseRestException):

    def __init__(self, message):
        super(AlertAlreadyExistsException, self).__init__(http.client.BAD_REQUEST, message)


logger = log.getLogger()


class EmAlertInterfaceImpl(object):
    """The Alert Interface that allows CRUD operations on alert definitions."""

    def __init__(self, session_key, system_session_key=''):
        self.session_key = session_key
        self.system_session_key = system_session_key
        self.managed_prefix = '%s:' % em_constants.APP_NAME
        self._setup_savedsearch_manager()

    def _setup_savedsearch_manager(self):
        logger.info('Setting up Savedsearch manager...')
        self.savedsearch_manager = SavedSearchManager(
            session_key=self.session_key,
            server_uri=em_common.get_server_uri(),
            app=em_constants.APP_NAME,
            system_session_key=self.system_session_key,
        )

    def handle_create_alert(self, request):
        alert = self._build_alert(request.data)
        existing_alert = None
        try:
            existing_alert = self.savedsearch_manager.get(alert.name)
        except Exception:
            pass
        if existing_alert is not None:
            raise AlertAlreadyExistsException(_('Alert with the specified name already exists.'))
        response = self.savedsearch_manager.create(alert.to_params())
        entry = self._parse_search_response(response)
        if len(entry) == 1:
            return entry[0]

    def handle_update_alert(self, request, alert_name):
        data = {'name': alert_name}
        data.update(request.data)
        alert = self._build_alert(data)
        alert_params = alert.to_params()
        # name in data body should be only used for creation
        del alert_params['name']
        response = self.savedsearch_manager.update(alert_name, alert_params)
        entry = self._parse_search_response(response)
        if len(entry) == 1:
            return entry[0]
        raise AlertInternalException(_('Unable to update alert'))

    def handle_delete_alert(self, request, alert_name):
        self.handle_get_alert(request, alert_name)
        try:
            self.savedsearch_manager.delete(alert_name)
        except Exception as e:
            logger.error('Failed to delete alert %s -  error: %s' % (alert_name, e))
            raise AlertInternalException(_('Cannot delete alert with name %(alert_name)s'))

    def handle_list_alerts(self, request):
        count = request.query.get('count', 0)
        offset = request.query.get('offset', 0)
        search_conditions = [
            'eai:acl.app="%s"' % em_constants.APP_NAME,
            'actions="em_write_alerts"'
        ]
        search_result = self.savedsearch_manager.load(count, offset, ' AND '.join(search_conditions))
        return self._parse_search_response(search_result)

    def handle_get_alert(self, request, alert_name):
        search_result = self.savedsearch_manager.get(alert_name)
        if search_result is not None:
            entry = self._parse_search_response(search_result)
            if len(list(entry)) == 1:
                return entry[0]
        raise AlertNotFoundException(_('Unable to get alert definition with given name'))

    def _parse_search_response(self, search_result):
        entries = search_result.get('entry', [])
        return [self._parse_alert_entry(entry) for entry in entries]

    def _parse_alert_entry(self, search_result_entry):
        c = search_result_entry['content']
        hasEmailEnabled = em_common.convert_to_bool(c.get('action.em_send_email', False))
        hasVictorOpsEnabled = em_common.convert_to_bool(c.get('action.em_send_victorops', False))
        hasSlackEnabled = em_common.convert_to_bool(c.get('action.em_send_slack', False))
        hasWebhookEnabled = em_common.convert_to_bool(c.get('action.em_send_webhook', False))
        notifications = []
        result = {
            'name': search_result_entry['name'],
            'search': c.get('search', ''),
            'typeId': self._drop_app_prefix(c.get('alert.managedBy', '')),
        }
        if hasEmailEnabled:
            notifications.append(
                {
                    'when': c.get(
                        'action.em_send_email.param.email_when',
                        em_constants.NOTIFY_WHEN['IMPROVE_OR_DEGRADE']
                    ),
                    'via': 'email',
                    'to': em_common.string_to_list(c.get('action.em_send_email.param.email_to', ''), sep=',')
                }
            )
        if hasVictorOpsEnabled:
            notifications.append(
                {
                    'when': c.get(
                        'action.em_send_victorops.param.victorops_when',
                        em_constants.NOTIFY_WHEN['IMPROVE_OR_DEGRADE']
                    ),
                    'via': 'victorops'
                }
            )
        if hasWebhookEnabled:
            notifications.append(
                {
                    'when': c.get(
                        'action.em_send_webhook.param.webhook_when',
                        em_constants.NOTIFY_WHEN['IMPROVE_OR_DEGRADE']
                    ),
                    'via': 'customWebhook',
                    'to': c.get('action.em_send_webhook.param.webhook_url', '')
                }
            )
        if hasSlackEnabled:
            notifications.append(
                {
                    'when': c.get(
                        'action.em_send_slack.param.slack_when',
                        em_constants.NOTIFY_WHEN['IMPROVE_OR_DEGRADE']
                    ),
                    'via': 'slack',
                    'to': c.get('action.em_send_slack.param.webhook_url', '')
                }
            )
        result.update(notifications=notifications)
        return result

    def _drop_app_prefix(self, s):
        return s[len(self.managed_prefix):] if s.startswith(self.managed_prefix) else s

    def _build_threshold(self, threshold_info):
        """
        build a threshold object
        :param threshold_info: threshold info should contain threshold values like info_min, info_max etc
        :return: an instance of EMThreshold object
        """
        def get_threshold_value(name):
            return float(threshold_info.get(name, ''))
        return EMThreshold(
            info_min=get_threshold_value('info_min'),
            info_max=get_threshold_value('info_max'),
            warning_min=get_threshold_value('warning_min'),
            warning_max=get_threshold_value('warning_max'),
            critical_min=get_threshold_value('critical_min'),
            critical_max=get_threshold_value('critical_max'),
        )

    def _build_alert_actions(self, alert_action_info):
        """
        build alert actions based on caller args
        :param alert_action_info: alert action info should contain require parameters for a specific alert action
        :return: an alert action object
        """

        actions = []
        notifications = alert_action_info.get('notifications', [])

        for notification in notifications:
            via = notification.get('via', '')
            when = em_common.string_to_list(notification.get('when', ''), sep=',')
            action = ''
            if via == 'email':
                action = EMEmailAlertAction(
                    email_to=[email.strip() for email in notification.get('to', [])],
                    email_when=when,
                )
            elif via == 'victorops':
                action = EMVictorOpsAlertAction(
                    victorops_when=when
                )
            elif via == 'customWebhook':
                to = notification.get('to', '')
                action = EMWebhookAlertAction(
                    webhook_when=when,
                    webhook_url=to
                )
            elif via == 'slack':
                to = notification.get('to', '')
                action = EMSlackAlertAction(
                    slack_when=when,
                    webhook_url=to
                )
            else:
                continue
            actions.append(action)

        # add default write alert action
        write_alert_action = EMWriteAlertAction()
        actions.append(write_alert_action)

        return actions

    def _build_alert(self, data):
        """
        build alert savedsearch spl
        :param data.name: name of the alert
        :param data.managed_by_id: id of the entity/group that this alert belongs to
        :param data.managed_by_type: type of object that manages this alert
        :param data.metric_spl: base SPL that extract metric data
        :param data.metric_filters: filters for the metrics of the alert
        :return: an instance of EMAlert
        """
        missing = []

        def get_with_check(param):
            val = data.get(param, '')
            if not val:
                missing.append(param)
            return val

        name = get_with_check('name')
        metric_spl = get_with_check('metric_spl')
        managed_by_id = get_with_check('managed_by_id')
        managed_by_type = get_with_check('managed_by_type')
        metric_filters = data.get('metric_filters', [])
        if len(missing) > 0:
            raise AlertArgValidationException(
                _('Invalid alert. Missing required arguments: %s' % missing)
            )
        threshold = self._build_threshold(data)
        actions = self._build_alert_actions(data)
        if not isinstance(actions, list):
            actions = [actions]
        return EMAlert(
            name=name,
            managed_by=managed_by_id,
            managed_by_type=managed_by_type,
            metric_spl=metric_spl,
            threshold=threshold,
            actions=actions,
            metric_filters=metric_filters,
        )
