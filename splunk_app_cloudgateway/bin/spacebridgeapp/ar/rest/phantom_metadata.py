"""(C) 2020 Splunk Inc. All rights reserved."""
import json
import sys

from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from spacebridgeapp.ar.data.phantom_metadata import PhantomMetadata, generate_phantom_deployment_name
from spacebridgeapp.ar.storage.phantom_registration_info import (
    get_phantom_metadata, set_phantom_metadata, delete_phantom_metadata, NoRegisteredPhantomInstanceException
)
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.logging.setup_logging import setup_logging
from spacebridgeapp.messages.request_context import RequestContext
from spacebridgeapp.rest import async_base_endpoint
from spacebridgeapp.rest.clients.async_client import noverify_treq_instance
from spacebridgeapp.util.constants import PAYLOAD, STATUS, SPACEBRIDGE_APP_NAME
from twisted.internet import defer
from twisted.internet.error import ConnectError, DNSLookupError, InvalidAddressError, SSLError
from twisted.web import http

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + ".log", "rest_phantom_metadata")
ERROR_MESSAGE = 'message'
ERROR_CODE = 'code'


class PhantomMetadataHandler(async_base_endpoint.AsyncBaseRestHandler):
    """
    Handles REST requests for setting / querying info on a Phantom instance for use with AR and workflow automation.
    """

    def __init__(self, *args, **kwargs):
        self._treq = kwargs.pop('treq_client', None) or noverify_treq_instance()
        super(PhantomMetadataHandler, self).__init__(*args, **kwargs)
        self._kvstore = self.async_client_factory.kvstore_client()

    @defer.inlineCallbacks
    def async_get(self, request):
        context = RequestContext.from_rest_request(request)
        try:
            phantom_metadata = yield get_phantom_metadata(context, self._kvstore)
            defer.returnValue({
                STATUS: http.OK,
                PAYLOAD: phantom_metadata.to_dict()
            })
        except NoRegisteredPhantomInstanceException:
            defer.returnValue({
                STATUS: http.NO_CONTENT,
                PAYLOAD: 'No existing configuration'  # The payload attribute is required for all responses.
            })

    @defer.inlineCallbacks
    def async_post(self, request):
        context = RequestContext.from_rest_request(request)
        if PAYLOAD not in request:
            raise SpacebridgeApiRequestError('Request must contain a JSON payload containing the field "hostname" set '
                                             'to the Phantom hostname to use.', status_code=http.BAD_REQUEST)
        request_payload = json.loads(request[PAYLOAD])
        if 'username' not in request_payload or 'password' not in request_payload:
            raise SpacebridgeApiRequestError('Request must include a Phantom username and password.',
                                             status_code=http.BAD_REQUEST)
        phantom_metadata = PhantomMetadata.from_json(request_payload)
        username, password = request_payload['username'], request_payload['password']

        if request_payload.get('health_check_only', False):
            response = yield self._health_check(phantom_metadata, username, password)
        else:
            response = yield self._set_phantom_metadata(context, phantom_metadata, username, password)

        defer.returnValue(response)

    @defer.inlineCallbacks
    def _set_phantom_metadata(self, context, phantom_metadata, username, password):
        try:
            deployment_name = yield self._get_phantom_system_name(phantom_metadata, username, password)
            if not phantom_metadata.deployment_name:
                phantom_metadata.deployment_name = deployment_name
        except Exception as e:
            defer.returnValue(_handle_get_system_name_error(phantom_metadata, e))

        yield set_phantom_metadata(context, self._kvstore, phantom_metadata)
        defer.returnValue({
            STATUS: http.OK,
            PAYLOAD: phantom_metadata.to_dict(include_key=False)
        })

    @defer.inlineCallbacks
    def _health_check(self, phantom_metadata, username, password):
        try:
            system_name = yield self._get_phantom_system_name(phantom_metadata, username, password)
            if not phantom_metadata.deployment_name:
                phantom_metadata.deployment_name = system_name
            defer.returnValue({
                PAYLOAD: phantom_metadata.to_dict(include_key=False),
                STATUS: http.OK
            })
        except Exception as e:
            defer.returnValue(_handle_get_system_name_error(phantom_metadata, e))

    @defer.inlineCallbacks
    def _get_phantom_system_name(self, phantom_metadata, username, password):
        system_settings_uri = '{phantom_domain}/rest/system_settings?sections=company_info_settings'.format(
            phantom_domain=phantom_metadata.domain)
        system_settings_response = yield self._treq.get(url=system_settings_uri.encode('utf-8'),
                                                        auth=(username, password))
        if system_settings_response.code != http.OK:
            message = yield system_settings_response.text()
            raise SpacebridgeApiRequestError(message, status_code=system_settings_response.code)
        system_settings_json = yield system_settings_response.json()
        defer.returnValue(system_settings_json.get('company_info_settings', {}).get('system_name',
                                                                                    generate_phantom_deployment_name()))

    @defer.inlineCallbacks
    def async_delete(self, request):
        context = RequestContext.from_rest_request(request)
        yield delete_phantom_metadata(context, self._kvstore)
        defer.returnValue({
            STATUS: http.OK,
            PAYLOAD: {'success': True}
        })


def _handle_get_system_name_error(phantom_metadata, e):
    if isinstance(e, DNSLookupError):
        LOGGER.exception('Unable to find locate domain=%s', phantom_metadata.domain)
        return {
            PAYLOAD: {
                ERROR_CODE: 1,
                ERROR_MESSAGE: ('Unable to locate Phantom at "{}". Make sure your Phantom and Splunk instances are on '
                                'the same network.'.format(phantom_metadata.domain))
            },
            STATUS: http.BAD_REQUEST
        }
    if isinstance(e, SSLError):
        LOGGER.exception('SSL error encountered when connecting to hostname=%s', phantom_metadata.hostname)
        return {
            PAYLOAD: {
                ERROR_CODE: 2,
                ERROR_MESSAGE: 'Encountered SSL error with Phantom host "{}". Make sure your Phantom host '
                               'has a valid certificate.'.format(phantom_metadata.hostname)
            },
            STATUS: http.BAD_REQUEST
        }
    if isinstance(e, InvalidAddressError):
        LOGGER.exception('Invalid address hostname=%s domain=%s', phantom_metadata.hostname, phantom_metadata.domain)
        return {
            PAYLOAD: {
                ERROR_CODE: 3,
                ERROR_MESSAGE: 'Invalid host format. Enter a Phantom host name without a '
                               'schema. For example, enter my-phantom-host instead of https://my-phantom-host/.'
            },
            STATUS: http.BAD_REQUEST
        }
    if isinstance(e, ConnectError):
        LOGGER.exception('Failed to connect to hostname=%s', phantom_metadata.hostname)
        return {
            PAYLOAD: {
                ERROR_CODE: 4,
                ERROR_MESSAGE: 'Unable to connect to Phantom host at "{}". Verify that this is the '
                               'location of your Phantom instance.'.format(phantom_metadata.domain)
            },
            STATUS: http.BAD_REQUEST
        }
    if isinstance(e, SpacebridgeApiRequestError):
        LOGGER.exception('Got a non-200 response from Phantom at hostname=%s message="%s" status_code=%d',
                         phantom_metadata.hostname, e.message, e.status_code)
        http_status_code_to_message = {
            http.UNAUTHORIZED: 'Invalid credentials. Try again.',
            http.FORBIDDEN: 'You don\'t have permission to check the status of this Phantom instance.',
        }
        return {
            PAYLOAD: {
                ERROR_CODE: e.status_code,
                ERROR_MESSAGE: (http_status_code_to_message.get(e.status_code) +
                                ' Make sure your Phantom and Splunk instances are on the same network, or contact your '
                                'Phantom administrator.')
            },
            STATUS: http.BAD_REQUEST
        }

    raise e
