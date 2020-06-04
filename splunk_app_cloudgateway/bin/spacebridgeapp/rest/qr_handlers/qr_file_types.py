"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint for getting a list of supported QR code image types by the
qr_code API. These image types will be available to download from the
UI
"""

import sys
from splunk.persistconn.application import PersistentServerConnectionApplication
from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.rest.services.qr_code_service import get_valid_file_types
from spacebridgeapp.rest.base_endpoint import BaseRestHandler

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + ".log", "rest_qr_file_types")


class QrFileTypes(BaseRestHandler, PersistentServerConnectionApplication):
    """
    Main class for handling the devices_user endpoint. Subclasses the spacebridge_app
    BaseRestHandler.
    """

    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)

    def get(self, request):
        """
        Handler which returns a list of file extension types
        """

        LOGGER.info('Returned list of supported QR code file download types to user=%s' % request['session']['user'])
        return {
            'payload': get_valid_file_types(with_names=True),
            'status': 200,
        }
