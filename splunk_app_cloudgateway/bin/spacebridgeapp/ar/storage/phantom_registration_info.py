"""
(C) 2020 Splunk Inc. All rights reserved.

Utilities for getting and setting an associated Phantom instance to use in conjunction with this Splunk instance and the
AR app.
"""
import json

from spacebridgeapp.util import py23
from spacebridgeapp.ar.data.phantom_metadata import PhantomMetadata
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.logging.setup_logging import setup_logging
from spacebridgeapp.util.constants import SPACEBRIDGE_APP_NAME
from twisted.internet import defer
from twisted.web import http

LOGGER = setup_logging(logfile_name='{}_phantom_registration_info'.format(SPACEBRIDGE_APP_NAME),
                       logger_name='phantom_registration_info')
PHANTOM_METADATA_COLLECTION = 'ar_phantom_metadata'


class NoRegisteredPhantomInstanceException(SpacebridgeApiRequestError):
    def __init__(self):
        super(NoRegisteredPhantomInstanceException, self).__init__(
            message='No Phantom instance has been registered with this Splunk instance yet.',
            status_code=http.NOT_FOUND)


@defer.inlineCallbacks
def get_phantom_metadata(request_context, kvstore_client):
    """
    Retrieves data about the Phantom instance associated with this Splunk instance for use with AR.

    :param request_context: The RequestContext of the request.
    :param kvstore_client: An AsyncKvStoreClient for looking up data from KV store.
    :return: a PhantomMetadata instance
    :raises: NoRegisteredPhantomInstanceException if there is no Phantom instance associated with this Splunk.
    """
    phantom_metadata_response = yield kvstore_client.async_kvstore_get_request(
        collection=PHANTOM_METADATA_COLLECTION, auth_header=request_context.auth_header, key_id=PhantomMetadata.key)
    if phantom_metadata_response.code == http.NOT_FOUND:
        raise NoRegisteredPhantomInstanceException()
    if phantom_metadata_response.code != http.OK:
        message = yield phantom_metadata_response.text()
        raise SpacebridgeApiRequestError(
            'Unable to fetch Phantom registration information message="{}" status_code={}'.format(
                message, phantom_metadata_response.code), status_code=phantom_metadata_response.code)
    phantom_metadata_json = yield phantom_metadata_response.json()
    defer.returnValue(PhantomMetadata.from_json(phantom_metadata_json))


@defer.inlineCallbacks
def set_phantom_metadata(request_context, kvstore_client, phantom_metadata):
    """
    Associates a Phantom instance for use with AR with this Splunk instance.

    :param request_context: The RequestContext of the request.
    :param kvstore_client: An AsyncKvStoreClient for storing Phantom metadata
    :param phantom_metadata: A PhantomMetadata instance containing the information about Phantom to set.
    """
    existing_metadata = None
    try:
        existing_metadata = yield get_phantom_metadata(request_context, kvstore_client)
        if phantom_metadata == existing_metadata:
            LOGGER.info('New Phantom metadata is the same as the existing one.')
            return
    except NoRegisteredPhantomInstanceException:
        LOGGER.debug('No existing phantom metadata found. No need to check whether the hostname has changed.')

    if existing_metadata:
        response = yield kvstore_client.async_kvstore_post_request(
            collection=PHANTOM_METADATA_COLLECTION,
            auth_header=request_context.auth_header,
            key_id=phantom_metadata.key,
            data=phantom_metadata.to_json())
    else:
        response = yield kvstore_client.async_kvstore_post_request(
            collection=PHANTOM_METADATA_COLLECTION,
            auth_header=request_context.auth_header,
            data=phantom_metadata.to_json())

    if response.code not in {http.OK, http.CREATED}:
        message = yield response.text()
        raise SpacebridgeApiRequestError(
            'Failed to set Phantom metadata KV store entry message="{}" status_code={}'.format(message, response.code),
            status_code=response.code)


@defer.inlineCallbacks
def delete_phantom_metadata(request_context, kvstore_client):
    """
    Clears any data about the associated Phantom instance if there was one.

    :param request_context: The RequestContext for the request.
    :param kvstore_client: An AsyncKvStoreClient to erase Phantom data with.
    """
    response = yield kvstore_client.async_kvstore_delete_request(collection=PHANTOM_METADATA_COLLECTION,
                                                                 auth_header=request_context.auth_header)
    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError(
            'Failed to clear Phantom metadata message="{}" status_code={}'.format(message, response.code),
            status_code=response.code)
