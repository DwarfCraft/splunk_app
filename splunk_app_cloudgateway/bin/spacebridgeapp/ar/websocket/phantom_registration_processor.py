"""
(C) 2020 Splunk Inc. All rights reserved.

Handles requests to start a new Spacebridge registration between an AR iOS client and a Phantom instance that resides
on the same network as this Splunk instance.

For more info see: https://docs.google.com/document/d/15vulwwovlVhT1hV6p2XyggVgCZPsmLpiqMlHUMb3tTI/edit?usp=sharing
"""
from spacebridgeapp.util import py23

from spacebridgeapp.ar.storage.phantom_registration_info import get_phantom_metadata
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.rest.clients.async_client import noverify_treq_instance
from twisted.internet import defer
from twisted.web import http

REGISTRATION_ID_FIELD = 'id'
DATA_FIELD = 'data'
CLIENT_ID_FIELD = 'client_id'
PHANTOM_DEVICE_NAME_CHARACTER_LIMIT = 25


@defer.inlineCallbacks
def process_phantom_registration_request(request_context, client_single_request, server_single_response,
                                         async_kvstore_client, treq_client=noverify_treq_instance()):
    """
    Starts a new registration between an AR client and Phantom and responds with Phantom's client ID for the new
    registration.

    :param request_context: The RequestContext for the request
    :param client_single_request: The ClientSingleRequest protobuf message.
    :param server_single_response: The ServerSingleResponse protobuf message.
    :param async_kvstore_client: An AsyncKvStore for looking up the Phantom hostname to use.
    :param treq_client: A Treq HTTPClient to use for making requests to Phantom and Spacebridge.
    """
    phantom_registration_request = client_single_request.createPhantomRegistrationRequest
    _validate_request(phantom_registration_request)

    # Look up which phantom instance is associated with this Splunk instance
    phantom_metadata = yield get_phantom_metadata(request_context, async_kvstore_client)

    # Hand off the auth code from retrieved device side to Phantom to kick off registration.
    registration_id = yield _start_phantom_registration(treq_client, phantom_metadata, phantom_registration_request)

    # Validate the confirmation code sent back from Phantom.
    phantom_client_id = yield _confirm_phantom_registration(treq_client, phantom_metadata, phantom_registration_request,
                                                            registration_id)

    server_single_response.createPhantomRegistrationResponse.phantom_client_id = phantom_client_id


def _validate_request(create_phantom_registration_request_pb):
    if create_phantom_registration_request_pb.auth_code == '':
        raise SpacebridgeApiRequestError('Must specify an auth code.', status_code=http.BAD_REQUEST)
    if create_phantom_registration_request_pb.device_client_id == '':
        raise SpacebridgeApiRequestError('Must specify device client ID.', status_code=http.BAD_REQUEST)
    if (create_phantom_registration_request_pb.device_name == ''
        or len(create_phantom_registration_request_pb.device_name) > PHANTOM_DEVICE_NAME_CHARACTER_LIMIT):
        raise SpacebridgeApiRequestError('Must specify a device name with no more than 25 characters.',
                                         status_code=http.BAD_REQUEST)
    if (create_phantom_registration_request_pb.phantom_creds.username == ''
        or create_phantom_registration_request_pb.phantom_creds.password == ''):
        raise SpacebridgeApiRequestError('Must specify a Phantom username and password.', status_code=http.BAD_REQUEST)


@defer.inlineCallbacks
def _start_phantom_registration(treq_client, phantom_metadata, phantom_registration_request):
    uri = '{phantom_domain}/rest/device_profile'.format(phantom_domain=phantom_metadata.domain)
    payload = {
        'auth_code': phantom_registration_request.auth_code,
        'name': phantom_registration_request.device_name,
    }
    auth = (phantom_registration_request.phantom_creds.username, phantom_registration_request.phantom_creds.password)
    start_registration_response = yield treq_client.post(url=uri.encode('utf-8'), json=payload, auth=auth)
    if start_registration_response.code != http.OK:
        message = yield start_registration_response.text()
        raise SpacebridgeApiRequestError(
            'Unable to start registration with Phantom message={} status_code={}'.format(
                message, start_registration_response.code), status_code=start_registration_response.code)
    start_registration_json = yield start_registration_response.json()

    defer.returnValue(start_registration_json[REGISTRATION_ID_FIELD])


@defer.inlineCallbacks
def _confirm_phantom_registration(treq_client, phantom_metadata, phantom_registration_request, registration_id):
    uri = '{phantom_domain}/rest/device_profile/{registration_id}'.format(
        phantom_domain=phantom_metadata.domain, registration_id=registration_id)
    payload = {
        'complete_registration': True,
        'username': phantom_registration_request.phantom_creds.username,
        'password': phantom_registration_request.phantom_creds.password,
    }
    auth = (phantom_registration_request.phantom_creds.username, phantom_registration_request.phantom_creds.password)
    confirm_registration_response = yield treq_client.post(url=uri.encode('utf-8'), json=payload, auth=auth)
    if confirm_registration_response.code != http.OK:
        message = yield confirm_registration_response.text()
        raise SpacebridgeApiRequestError(
            'Unable to confirm registration_id={} with Phantom message={} status_code={}'.format(
                registration_id, message, confirm_registration_response.code),
            status_code=confirm_registration_response.code)
    confirm_registration_json = yield confirm_registration_response.json()

    defer.returnValue(confirm_registration_json[DATA_FIELD][CLIENT_ID_FIELD])


@defer.inlineCallbacks
def process_get_phantom_registration_info(request_context, client_single_request, server_single_response,
                                          async_kvstore_client):
    phantom_metadata = yield get_phantom_metadata(request_context, async_kvstore_client)
    server_single_response.getPhantomRegistrationInfoResponse.deployment_name = phantom_metadata.deployment_name
    server_single_response.getPhantomRegistrationInfoResponse.hostname = phantom_metadata.hostname
