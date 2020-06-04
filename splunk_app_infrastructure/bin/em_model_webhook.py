import em_path_inject  # noqa

from logging_utils import log
from solnlib import conf_manager
from splunk import getDefault
import em_constants
import http.client
from em_utils import get_conf_stanza
from utils.i18n_py23 import _

# set up logger
logger = log.getLogger()

WEBHOOK_CONF_FILE = 'webhook'
STANZA_NAME = 'default_settings'
CONF_WEBHOOK_KEY = 'webhook_url'
DISPLAY_WEBHOOK_KEY = 'url'
# empty webhook is represented by string composed of the empty string since the empty string does not save to conf file
CONF_EMPTY_WEBHOOK_URL = '""'
DISPLAY_EMPTY_WEBHOOK_URL = ''
CONF_EMPTY_WEBHOOK_URL_STANZA = {
    CONF_WEBHOOK_KEY: CONF_EMPTY_WEBHOOK_URL
}
WEBHOOK_REST_API_GET_ERROR_MESSAGE = _('Unable to fetch Custom Webhook.')
WEBHOOK_REST_API_UPDATE_ERROR_MESSAGE = _('Unable to update Custom Webhook.')


class InvalidWebhookException(Exception):
    pass


class EMWebhook(object):

    @staticmethod
    def convert_webhook_url_conf_to_display(webhook_url):
        """
        Converts url from how it is stored in conf file to how it will be displayed in REST response
        :param webhook_url: url formatted for REST response
        """
        if webhook_url == CONF_EMPTY_WEBHOOK_URL:
            return DISPLAY_EMPTY_WEBHOOK_URL
        else:
            return webhook_url

    @staticmethod
    def convert_webhook_url_display_to_conf(webhook_url):
        """
        Converts url from how it will be displayed in REST response to how it is stored in conf file
        :param webhook_url: url formatted for storage in conf file
        """
        if webhook_url == DISPLAY_EMPTY_WEBHOOK_URL:
            return CONF_EMPTY_WEBHOOK_URL
        else:
            return webhook_url

    @staticmethod
    def validate_webhook_url_format(webhook_url):
        """
        Throws an exception if custom webhook url is not properly formatted
        :param webhook_url: the custom webhook url taken in from request data
        """
        if not (webhook_url.startswith('http://') or webhook_url.startswith('https://')):
            raise InvalidWebhookException('Invalid webhook url provided')

    @classmethod
    def setup(cls, session_key):
        """
        Set up sesison key and conf manager.
        NOTE: Must be done before performing any further actions
        """
        cls.conf_manager = conf_manager.ConfManager(session_key, em_constants.APP_NAME, port=getDefault('port'))
        try:
            cls.conf = get_conf_stanza(cls.conf_manager, WEBHOOK_CONF_FILE)
        except Exception:
            return EMWebhook.error_rest_api_response(message=WEBHOOK_REST_API_GET_ERROR_MESSAGE)

    @classmethod
    def get(cls):
        """
        get the current default webhook url

        :return a dict that will be the returned as the response
        """
        try:
            # if the stanza is not there, default back to an empty url
            webhook_url = cls.conf.get(STANZA_NAME, CONF_EMPTY_WEBHOOK_URL_STANZA).get(CONF_WEBHOOK_KEY,
                                                                                       CONF_EMPTY_WEBHOOK_URL)
            logger.info('Default webhook url retrieved from conf file: "%s"' % (webhook_url))
            return EMWebhook.successful_rest_api_response(webhook_url=webhook_url)
        except Exception as e:
            logger.error('Failed to load webhook stanza with name %s: %s' % (STANZA_NAME, e))
            return EMWebhook.error_rest_api_response(message=WEBHOOK_REST_API_GET_ERROR_MESSAGE)

    @classmethod
    def update(cls, webhook_url):
        """
        update default webhook url

        :param webhook_url: the new webhook url to use
        :return a dict that will be the returned as the response
        """
        try:
            webhook_url = EMWebhook.convert_webhook_url_display_to_conf(webhook_url)
            updated_stanza = {
                CONF_WEBHOOK_KEY: webhook_url,
            }
            cls.conf.update(STANZA_NAME, updated_stanza)
            logger.info('Default webhook url updated to conf file: "%s"' % (webhook_url))
            return EMWebhook.successful_rest_api_response(webhook_url=webhook_url)
        except Exception as e:
            logger.error('Failed to update webhook stanza with name %s: %s' % (STANZA_NAME, e))
            return EMWebhook.error_rest_api_response(message=WEBHOOK_REST_API_UPDATE_ERROR_MESSAGE)

    @staticmethod
    def successful_rest_api_response(webhook_url):
        return EMWebhook.rest_api_response(webhook_url, message='', error=False)

    @staticmethod
    def error_rest_api_response(message):
        return EMWebhook.rest_api_response(CONF_EMPTY_WEBHOOK_URL, message=message, error=True)

    @staticmethod
    def rest_api_response(webhook_url, message, error=False):
        """
        Builds the response
        :param webhook_url: the webhook url from the request
        :param message: the message to include in the response
        :param error: whether to return an error message
        :return a tuple with the first element an integer representing the status code
        and the second element representing the response(either a string or dict depending in status code)
        """
        if error:
            return (http.client.BAD_REQUEST, message)
        else:
            response_dict = {
                DISPLAY_WEBHOOK_KEY: EMWebhook.convert_webhook_url_conf_to_display(webhook_url)
            }
            return (http.client.OK, response_dict)
