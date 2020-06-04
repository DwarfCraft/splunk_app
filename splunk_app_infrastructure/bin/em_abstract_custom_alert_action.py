from builtins import object
import em_path_inject  # noqa
import sys
import em_constants
import json
import splunk.rest as rest
import splunk.entity as entity
import em_common as EMCommon
from abc import ABCMeta, abstractmethod
from splunklib.client import Service
from rest_handler.session import session
from logging_utils import log
from future.utils import with_metaclass


logger = log.getLogger()


class CustomAlertActionException(Exception):
    pass


class AbstractCustomAlertAction(with_metaclass(ABCMeta, object)):
    """
    Abstract class holds common opetations across alert actions.
    """

    def __init__(self):
        self._service = None
        self.session_key = None
        self.sid = None
        self.search_name = None
        self.namespace = None

    def get_alert_action_setting(self, alert_action_type):
        """
        Fetches the email alert settings
        """
        settings = None
        try:
            settings = entity.getEntity(
                '/configs/conf-alert_actions',
                alert_action_type,
                sessionKey=self.session_key, owner='nobody', namespace=self.namespace)
        except Exception as e:
            logger.error('Could not access or parse %s stanza of alert_actions.conf. Error=%s'
                         % (alert_action_type, str(e)))
        return settings

    def _make_base_url(self, custom_hostname=None):
        """
        Makes the base url from custom hostname
        """
        if custom_hostname:
            return custom_hostname
        splunkweb_url = EMCommon.get_splunkweb_fqdn()
        if not EMCommon.is_splunk_cloud(splunkweb_url):
            return splunkweb_url
        else:
            return splunkweb_url.rsplit(":", 1)[0]

    def process_payload(self, payload):
        """
        Fetches the search results by using the sid from the payload
        """
        self.sid = payload.get('sid')
        self.search_name = payload.get('search_name')
        self.session_key = payload.get('session_key')
        self.namespace = payload.get('namespace', 'splunk_app_infrastructure')

        logger.info('custom alert action triggered, search_name = %s' % self.search_name)
        endpoint = em_constants.SEARCH_RESULTS_ENDPOINT % (EMCommon.get_server_uri(), em_constants.APP_NAME, self.sid)
        getargs = {'output_mode': 'json', 'count': 0}
        _, content = rest.simpleRequest(endpoint, self.session_key, method='GET', getargs=getargs)
        return json.loads(content)

    @property
    def service(self):
        if not self.session_key:
            raise CustomAlertActionException('session key not set before accessing service')
        if self._service:
            return self._service
        self._service = Service(token=self.session_key, app=em_constants.APP_NAME, owner='nobody')
        return self._service

    def run(self):
        """
        called in the __main__ block of each the alert action.
        """
        # run the script
        if len(sys.argv) > 1 and sys.argv[1] == '--execute':
            try:
                payload = json.loads(sys.stdin.read())
                self.execute_action(payload)
            except Exception as e:
                logger.error(e)
                sys.exit(3)
        else:
            logger.error('FATAL Unsupported execution mode (expected --execute flag)')
            sys.exit(1)

    def execute_action(self, payload):
        """
        Processes the payload and calls the alert specific execute function to perform actions
        on the search results
        """
        try:
            content = self.process_payload(payload)
            # save authtoken into session
            session.save(authtoken=self.session_key)

            results = content['results']
            self.execute(results, payload)
            # clear session
        finally:
            session.clear()

    @abstractmethod
    def execute(self, result, payload):
        """
        All child class should override this method to perform custom actions on the results
        """
        raise NotImplementedError()
