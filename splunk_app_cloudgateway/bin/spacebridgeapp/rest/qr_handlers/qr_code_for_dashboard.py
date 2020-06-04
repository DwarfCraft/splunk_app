"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for downloading a QR code based on a specific dashboard id
"""

import sys
from splunk.persistconn.application import PersistentServerConnectionApplication
from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.rest.base_endpoint import BaseRestHandler
from spacebridgeapp.rest.util.helper import extract_parameter
from spacebridgeapp.rest.util import errors as Errors
from spacebridgeapp.rest.services.qr_code_service import generate_qr_code
from spacebridgeapp.rest.services.qr_code_service import get_valid_file_types
from spacebridgeapp.dashboard.dashboard_helpers import shorten_dashboard_id_from_url

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + ".log", "rest_qr_code_for_dashboard")

DASHBOARD_ID_LABEL = 'dashboard_id'
QR_CODE_DASHBOARD_VERSION = '1'


class QrCodeForDashboard(BaseRestHandler, PersistentServerConnectionApplication):
    """
    Main class for handling the devices_user endpoint. Subclasses the spacebridge_app
    BaseRestHandler.
    """

    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)

    def get(self, request):
        """
        Handler which generates QR codes using a deep link generated from a dashboard ID, and
        returns it to the client as a binary body of the specified type. This function:
            1. Extracts request data
            2. Validates the requested file type
            3. Validates and transforms the dashboard ID into a deep link
            4. Generates and returns the QR code
        """
        # Extracts request data
        user = request['session']['user']
        dashboard_id = extract_parameter(request['query'], DASHBOARD_ID_LABEL, 'query')
        file_type = request['path_info'].split('.')[-1]
        id_type = 'a' if 'isAr' in request['query'] else 's'

        # Validates the requested file type
        if file_type not in get_valid_file_types(with_names=False):
            raise Errors.SpacebridgeRestError('QR code was requested with invalid file_type=%s' % file_type)

        # Validates and transforms the dashboard ID into a deep link
        deep_link = shorten_dashboard_id_from_url(dashboard_id)
        if deep_link == dashboard_id:  # Nothing was shortened so it must be an invalid dashboard_id
            raise Errors.SpacebridgeRestError('QR code was requested for invalid dashboard_id=%s' % dashboard_id)
        deep_link = 'https://spl.mobi/%s%s/%s' % (id_type, QR_CODE_DASHBOARD_VERSION, deep_link)

        LOGGER.info('Generated QR code of deep_link=%s for user=%s' % (deep_link, user))

        # Generates and returns the QR code
        return {
            'binary': generate_qr_code(deep_link, file_type),
            'status': 200,
        }
