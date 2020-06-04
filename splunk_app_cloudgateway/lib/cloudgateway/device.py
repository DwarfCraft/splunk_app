"""
(C) 2019 Splunk Inc. All rights reserved.
"""
import sys
from cloudgateway import py23
import base64
import collections

"""Wrapper Credentials Bundle object to store a session token and username which are returned by the 
server side on registration
"""
CredentialsBundle = collections.namedtuple('CredentialsBundle', 'session_token username deployment_name server_type')


def make_device_id(encryption_context, sign_public_key):
    return encryption_context.generichash_raw(sign_public_key)


class DeviceInfo(object):
    """
    Helper class to encapsulate a client device's credentials that are returned by cloudgateway when we initiate
    the registration process
    """

    def __init__(self, encrypt_public_key, sign_public_key, device_id="", confirmation_code="", app_id="",
                 client_version="", app_name=""):
        self.encrypt_public_key = encrypt_public_key  # binary value
        self.sign_public_key = sign_public_key  # binary value
        self.device_id = device_id  # binary value
        self.confirmation_code = confirmation_code  # string
        self.app_id = app_id  # string
        self.client_version = client_version  # string
        self.app_name=app_name

    def __repr__(self):
        return str(self.__dict__)

    def to_json(self):

        if sys.version_info < (3, 0):
            encrypt_public_key = base64.b64encode(self.encrypt_public_key)
            sign_public_key = base64.b64encode(self.sign_public_key)
            device_id =base64.b64encode(self.device_id)
        else:
            encrypt_public_key = base64.b64encode(self.encrypt_public_key).decode('ascii')
            sign_public_key = base64.b64encode(self.sign_public_key).decode('ascii')
            device_id = base64.b64encode(self.device_id).decode('ascii')


        return {
                    'encrypt_public_key': encrypt_public_key,
                    'sign_public_key': sign_public_key,
                    'device_id': device_id,
                    'conf_code': self.confirmation_code,
                    'app_id': self.app_id,
                    'client_version': self.client_version,
                    'app_name': self.app_name

               }

    @staticmethod
    def from_json(jsn):
        return DeviceInfo(
           base64.b64decode(jsn['encrypt_public_key']),
           base64.b64decode(jsn['sign_public_key']),
           base64.b64decode(jsn['device_id']),
           jsn['conf_code'],
           jsn['app_id'],
           jsn['client_version'],
        )


class EncryptionKeys(object):
    """
    Data class to encapsulate public and private keys needed to communicate with a device over cloud gatewaay

    """
    def __init__(self, sign_public_key, sign_private_key, encrypt_public_key, encrypt_private_key):
        """

        :param sign_public_key:
        :param sign_private_key:
        :param encrypt_public_key:
        :param encrypt_private_key:
        """
        self.sign_public_key = sign_public_key
        self.sign_private_key = sign_private_key
        self.encrypt_public_key = encrypt_public_key
        self.encrypt_private_key = encrypt_private_key

    def __repr__(self):
        return str(self.__dict__)

    def to_json(self):
        if sys.version_info < (3, 0):
            encrypt_public_key = base64.b64encode(self.encrypt_public_key)
            encrypt_private_key= base64.b64encode(self.encrypt_private_key)
            sign_public_key = base64.b64encode(self.sign_public_key)
            sign_private_key = base64.b64encode(self.sign_private_key)

        else:
            encrypt_public_key = base64.b64encode(self.encrypt_public_key).decode('ascii')
            encrypt_private_key= base64.b64encode(self.encrypt_private_key).decode('ascii')
            sign_public_key = base64.b64encode(self.sign_public_key).decode('ascii')
            sign_private_key = base64.b64encode(self.sign_private_key).decode('ascii')


        return {
            'encrypt_public_key': encrypt_public_key,
            'encrypt_private_key': encrypt_private_key,
            'sign_public_key': sign_public_key,
            'sign_private_key': sign_private_key

        }

    @staticmethod
    def from_json(jsn):

        return EncryptionKeys(
            base64.b64decode(jsn['sign_public_key']),
            base64.b64decode(jsn['sign_private_key']),
            base64.b64decode(jsn['encrypt_public_key']),
            base64.b64decode(jsn['encrypt_private_key'])
        )
