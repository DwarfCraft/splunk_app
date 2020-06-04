from future.moves.urllib.request import urlopen, Request
import json
import sys
from os import path
import utils

lib_dir = path.dirname(path.dirname(path.abspath(__file__)))  # noqa
sys.path.append(lib_dir)  # noqa
from . import BaseServiceManager, BaseServiceManagerException
from logging_utils import log

INTEGRATION_URL = "https://alert.victorops.com/integrations/generic/20131114/alert"

logger = log.getLogger()


class VictorOpsCouldNotSendAlertException(BaseServiceManagerException):
    def __init__(self, message):
        super(BaseServiceManagerException, self).__init__(message)


class VictorOpsManager(BaseServiceManager):

    """
    Manager class that handles all kinds of communication
    with VictorOps REST API
    """
    def __init__(self, api_key, routing_key, monitoring_tool):
        super(VictorOpsManager, self).__init__()
        self.api_key = api_key
        self.routing_key = routing_key
        self.monitoring_tool = monitoring_tool

    def send_incident(self, incident):
        """
        send incident to VictorOps

        :param incident: a dict that contains key/value info of the incident
        """
        try:
            url = "%s/%s/%s" % (INTEGRATION_URL, self.api_key, self.routing_key)
            headers = {
                'content-type': 'application/json',
            }
            incident.update({
                'monitoring_tool': self.monitoring_tool
            })
            req = Request(url, utils.to_bytes(json.dumps(incident)), headers)
            response = urlopen(req)
            message, status_code = response.msg, response.code
            if status_code != 200:
                raise VictorOpsCouldNotSendAlertException("status_code=%s, message=%s" % (status_code, message))
        except Exception as e:
            logger.error("Failed to send incident to VictorOps because: %s", e)
            raise VictorOpsCouldNotSendAlertException(str(e))
