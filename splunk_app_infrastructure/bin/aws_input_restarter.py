# Copyright 2016 Splunk Inc. All rights reserved.
# Environment configuration
import em_path_inject  # noqa
import json
import sys
import traceback

import em_common
import em_constants
from builtins import str
from em_utils import get_check_internal_log_message
from future.moves.urllib.error import HTTPError
from future.moves.urllib.parse import urlencode
from future.moves.urllib.request import urlopen, Request
from modinput_wrapper.base_modularinput import BaseModularInput
from splunk import getDefault
from splunklib.client import Service
from splunklib.modularinput import Argument
from utils import to_bytes
from logging_utils import log

logger = log.getLogger()


class AWSInputRestarter(BaseModularInput):
    """
    AWS Input Restarter
    This ModInput restarts certain AWS inputs to workaround TA-AWS bugs
    """

    app = em_constants.APP_NAME
    name = "aws_input_restarter"
    title = "Splunk App for Infrastructure - AWS Input Restarter"
    description = "Restarts certain AWS inputs to workaround TA-AWS bugs"
    use_external_validation = False
    use_kvstore_checkpointer = False
    use_hec_event_writer = False
    use_single_instance = True

    def __init__(self):
        super(AWSInputRestarter, self).__init__()
        self.splunkd_messages_service = None

    def extra_arguments(self):
        return [
            {
                'name': 'log_level',
                'title': 'Log level',
                'description': 'The logging level of the modular input. Defaults to INFO',
                'required_on_create': False,
                'data_type': Argument.data_type_string
            }
        ]

    def do_additional_setup(self):
        log_level = self.inputs.get('restarter').get('log_level', 'INFO')
        logger.setLevel(log.parse_log_level(log_level))
        self.splunkd_messages_service = Service(
                                                port=getDefault('port'),
                                                token=self.session_key,
                                                app=em_constants.APP_NAME,
                                                owner='nobody').messages

    def do_execute(self):
        try:
            if not em_common.modular_input_should_run(self.session_key):
                logger.info("Skipping aws_input_restarter modinput execution on non-captain node.")
                return

            request = self._generate_cloudwatch_input_request('GET')

            logger.info('Fetching AWS CloudWatch inputs...')
            response = urlopen(request)
            response = json.loads(response.read())

            # If there's an input, disable then enable it
            if not len(response.get('entry', [])):
                logger.info('No AWS CloudWatch inputs found, exiting...')
                return

            input_name = response['entry'][0]['name']
            logger.info('Attempting to restart AWS CloudWatch input: ' + input_name)
            disable_request = self._generate_cloudwatch_input_request(
                'POST',
                data={'disabled': 1},
                name=input_name)

            enable_request = self._generate_cloudwatch_input_request(
                'POST',
                data={'disabled': 0},
                name=input_name)

            logger.info('Disabling AWS CloudWatch input: ' + input_name)
            disable_response = urlopen(disable_request)
            disable_response = json.loads(disable_response.read())

            logger.info('Enabling AWS CloudWatch input: ' + input_name)
            enable_response = urlopen(enable_request)
            enable_response = json.loads(enable_response.read())

            logger.info('Modular input execution complete!')
        except HTTPError as err:
            if err.code == 404:
                logger.warning('AWS TA is not installed. Cannot run aws_input_restarter.')
                return
        except Exception:
            error_type, error, tb = sys.exc_info()
            message = 'AWS Input Restarter Modular input execution failed: ' + str(error)
            logger.error(message + '\nTraceback:\n' + ''.join(traceback.format_tb(tb)))
            link_to_error = get_check_internal_log_message()
            self.splunkd_messages_service.create(
                'aws-input-restarter-failure',
                severity='warn',
                value=('Failed to restart AWS data collection inputs.'
                       ' Newly added EC2 instances will cease to be detected. ' + link_to_error)
            )

    def _generate_cloudwatch_input_request(self, method, data=None, name=None):
        base_url = '%s/servicesNS/nobody/Splunk_TA_aws/splunk_ta_aws_aws_cloudwatch/%s?%s'
        headers = {
            'Authorization': 'Splunk %s' % self.session_key,
            'Content-Type': 'application/json'
        }

        # Handle the query params that are passed in
        server_uri = em_common.get_server_uri()
        query_params = dict(output_mode='json')
        query_params['count'] = 1
        query_params['offset'] = 0

        # Build the URL and make the request
        url = base_url % (server_uri, name or '', urlencode(query_params))
        request = Request(
            url,
            to_bytes(urlencode(data)) if data else None,
            headers=headers)
        request.get_method = lambda: method

        return request


if __name__ == '__main__':
    exit_code = AWSInputRestarter().execute()
    sys.exit(exit_code)
