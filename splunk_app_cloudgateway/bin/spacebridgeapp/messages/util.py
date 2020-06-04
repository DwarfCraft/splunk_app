import base64
import sys
from cloudgateway.device import DeviceInfo
from spacebridgeapp.util import py23
from spacebridgeapp.exceptions.key_not_found_exception import KeyNotFoundError
from spacebridgeapp.util.constants import DEVICE_PUBLIC_KEYS_COLLECTION_NAME
from twisted.internet import defer
from twisted.web import http


@defer.inlineCallbacks
def fetch_device_info(device_id, async_kvstore_client, system_auth_header):
    """
    Fetch the DeviceInfo for a particular device ic
    :param device_id:
    :param async_kvstore_client:
    :param system_auth_header:
    :return: cloudgateway.device.DeviceInfo
    """
    key_id = py23.urlsafe_b64encode_to_str(device_id)

    response = yield async_kvstore_client.async_kvstore_get_request(DEVICE_PUBLIC_KEYS_COLLECTION_NAME,
                                                                         auth_header=system_auth_header,
                                                                         key_id=key_id)

    if response.code == http.OK:
        parsed = yield response.json()
        result = DeviceInfo(
            base64.b64decode(parsed['encrypt_public_key']),
            base64.b64decode(parsed['sign_public_key']),
            device_id)

        defer.returnValue(result)
    else:
        raise KeyNotFoundError(key_id, response.code)

