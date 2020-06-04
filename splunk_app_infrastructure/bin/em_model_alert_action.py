from abc import ABCMeta, abstractmethod
import re
from future.utils import with_metaclass

from utils.i18n_py23 import _

from em_constants import NOTIFY_WHEN
from em_model_webhook import EMWebhook
from em_model_slack import EMSlack


class AlertActionInvalidArgsException(Exception):
    pass


class EMAlertAction(with_metaclass(ABCMeta, object)):
    """
    Abstract class of all alert actions
    """

    def __init__(self, action_name, **action_params):
        self.action_name = action_name
        for k, v in action_params.items():
            setattr(self, k, v)
        try:
            self.validate()
        except Exception as e:
            if isinstance(e, AlertActionInvalidArgsException):
                raise e
            raise AlertActionInvalidArgsException('Invalid alert action argument - Error: %s' % e)

    @abstractmethod
    def validate(self):
        """
        Override this method to validate action parameters
        :return:
        """
        pass

    def to_params(self):
        """
        turn action into savedsearch conf params foramt
        :return: dict
        """
        res = {}
        action_param = 'action.%s' % self.action_name
        for k, v in vars(self).items():
            if k != 'action_name':
                param_key = '%s.param.%s' % (action_param, k)
                if isinstance(v, list):
                    v = ','.join(v)
                res[param_key] = v
        return res


class EMVictorOpsAlertAction(EMAlertAction):
    """
    VictorOps alert action class
    """
    ACTION_NAME = 'em_send_victorops'
    SUPPORTED_VICTOROPS_NOTIFICATION_CRITERIA = [
        NOTIFY_WHEN['IMPROVE'],
        NOTIFY_WHEN['DEGRADE']
    ]

    def __init__(self,  victorops_when):
        if not isinstance(victorops_when, list):
            victorops_when = [victorops_when]

        super(EMVictorOpsAlertAction, self).__init__(
            action_name=EMVictorOpsAlertAction.ACTION_NAME,
            victorops_when=victorops_when
        )

    def validate(self):
        for criteria in self.victorops_when:
            if criteria not in EMVictorOpsAlertAction.SUPPORTED_VICTOROPS_NOTIFICATION_CRITERIA:
                raise AlertActionInvalidArgsException(
                    _('VictorOps notification criteria is not one of the supported criteria')
                )


class EMWebhookAlertAction(EMAlertAction):
    """
    Webhook alert action class
    """
    ACTION_NAME = 'em_send_webhook'
    SUPPORTED_WEBHOOK_NOTIFICATION_CRITERIA = [
        NOTIFY_WHEN['IMPROVE'],
        NOTIFY_WHEN['DEGRADE']
    ]

    def __init__(self, webhook_when, webhook_url):
        if not isinstance(webhook_when, list):
            webhook_when = [webhook_when]

        super(EMWebhookAlertAction, self).__init__(
            action_name=EMWebhookAlertAction.ACTION_NAME,
            webhook_when=webhook_when,
            webhook_url=webhook_url
        )

    def validate(self):
        for criteria in self.webhook_when:
            if criteria not in EMWebhookAlertAction.SUPPORTED_WEBHOOK_NOTIFICATION_CRITERIA:
                raise AlertActionInvalidArgsException(
                    _('Custom Webhook notification criteria is not one of the supported criteria')
                )
        EMWebhook.validate_webhook_url_format(self.webhook_url)


class EMSlackAlertAction(EMAlertAction):
    """
    Slack alert action class
    """
    ACTION_NAME = 'em_send_slack'
    SUPPORTED_SLACK_NOTIFICATION_CRITERIA = [
        NOTIFY_WHEN['IMPROVE'],
        NOTIFY_WHEN['DEGRADE']
    ]

    def __init__(self, slack_when, webhook_url):
        if not isinstance(slack_when, list):
            slack_when = [slack_when]

        super(EMSlackAlertAction, self).__init__(
            action_name=EMSlackAlertAction.ACTION_NAME,
            slack_when=slack_when,
            webhook_url=webhook_url
        )

    def validate(self):
        for criteria in self.slack_when:
            if criteria not in EMSlackAlertAction.SUPPORTED_SLACK_NOTIFICATION_CRITERIA:
                raise AlertActionInvalidArgsException(
                    _('Slack notification criteria is not one of the supported criteria')
                )
        EMSlack.validate_webhook_url_format(self.webhook_url)


class EMEmailAlertAction(EMAlertAction):
    """
    Email alert action class
    """
    ACTION_NAME = 'em_send_email'
    SUPPORTED_EMAIL_NOTIFICATION_CRITERIA = [
        NOTIFY_WHEN['IMPROVE'],
        NOTIFY_WHEN['DEGRADE']
    ]

    def __init__(self, email_to, email_when):
        if not isinstance(email_when, list):
            email_when = [email_when]
        if not isinstance(email_to, list):
            email_to = [email_to]
        super(EMEmailAlertAction, self).__init__(
            action_name=EMEmailAlertAction.ACTION_NAME,
            email_to=email_to,
            email_when=email_when
        )

    def validate(self):
        for criteria in self.email_when:
            if criteria not in EMEmailAlertAction.SUPPORTED_EMAIL_NOTIFICATION_CRITERIA:
                raise AlertActionInvalidArgsException(
                    _('Email notification criteria is not one of the supported criteria')
                )

        if not self.email_to or len(self.email_to) == 0:
            raise AlertActionInvalidArgsException(_('No email_to provided'))

        for email_address in self.email_to:
            if not email_address or not re.match(r"[^@]+@[^@]+\.[^@]+", email_address):
                raise AlertActionInvalidArgsException(_('Invalid email address provided'))


class EMWriteAlertAction(EMAlertAction):
    """
    Write alert to alert index custom action
    """
    ACTION_NAME = 'em_write_alerts'

    def __init__(self):
        super(EMWriteAlertAction, self).__init__(action_name=EMWriteAlertAction.ACTION_NAME)

    def validate(self):
        pass
