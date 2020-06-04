"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for the UI-to-NLPservice auth process. It
gets an single use token from the IMS service and passes it to the UI.
"""

import sys
import json
import base64
import time
import requests
import urllib
from functools import partial
import splunk.rest as rest
import splunk.entity as en
from splunk.persistconn.application import PersistentServerConnectionApplication
from splunk.clilib.bundle_paths import make_splunkhome_path


sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))

from spacebridgeapp.nlp.data.nlp_data import AuthToken

import spacebridgeapp.nlp.rest.utils as nlp_utils
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from cloudgateway.private.encryption.encryption_handler import  sign_detached, sign_verify
from cloudgateway.splunk.encryption import SplunkEncryptionContext
from cloudgateway.private.sodium_client import SodiumClient
from spacebridgeapp.rest.base_endpoint import BaseRestHandler
from spacebridgeapp.rest.services.kvstore_service import KVStoreCollectionAccessObject as KvStore
from spacebridgeapp.util.config import cloudgateway_config as config

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + ".log", "nlp_rest_ims_auth_handler")

NLP_WRITE_CAPABILITY = "nlp_write"
VERSION_API = "version"
DEFAULT_IMS_SERVER = "http://localhost:9992/nlp/ims/v1"

def get_nlp_ims_url(user, user_token, with_version):
    try:
        ent = en.getEntity(["configs", "conf-nlp"],
                           "config",
                           namespace=constants.SPACEBRIDGE_APP_NAME, owner=user,
                           sessionKey=user_token)
        url = ent["nlp_ims_server"] + '/nlp/ims' if "nlp_ims_server" in ent and nlp_utils.check_https(ent["nlp_ims_server"]) else None

        if 'nlp_ims_server_api_version' in ent and with_version:
            return url + '/' + ent['nlp_ims_server_api_version']
        else:
            return url
    except Exception as ex:
        LOGGER.info('Unable to get NLP server configuration, using default NLP server={}: {}'
                    .format(DEFAULT_IMS_SERVER, ex))

    return DEFAULT_IMS_SERVER

def get_nlp_device(user, user_token):
    try:
        params = {}
        serverResponse, serverContent = rest.simpleRequest("nlp/registration/query", getargs=params,
                                                       sessionKey=user_token)
        reg_query_result = json.loads(serverContent)
        return reg_query_result
    except Exception as ex:
        LOGGER.info('Unable to get NLP service device id: {}'
                    .format(ex))
    return None

def build_url(self, user, user_token, path):
    with_version = False if path == VERSION_API else True
    base_url = get_nlp_ims_url(user, user_token, with_version)
    encodedParts = urllib.quote(path)
    url_path = base_url + '/' + encodedParts
    return url_path

def generate_auth_token(self, user, user_token, deployment_id):
    mapped_user_id = nlp_utils.get_mapped_user_id(deployment_id, user)
    can_manage_intents = nlp_utils.user_has_capability(user, user_token, NLP_WRITE_CAPABILITY)
    current_milli_time = int(round(time.time() * 1000))
    return AuthToken(deployment_id, mapped_user_id, can_manage_intents, current_milli_time)

def generate_signed_auth_token(self, system_authtoken, auth_token):
    encryption_context = SplunkEncryptionContext(system_authtoken, constants.SPACEBRIDGE_APP_NAME, self.sodium_client)
    encryption_context._cache_keys()
    signer = partial(sign_detached, self.sodium_client, encryption_context.sign_private_key())
    return base64.b64encode(signer(auth_token.to_json().encode('utf-8')))

def get_headers(self, user, user_token, system_authtoken, request_headers):

    deployment_info = nlp_utils.get_deployment_info(user_token)
    deployment_id = deployment_info['deployment_id']

    auth_token = generate_auth_token(self, user, user_token, deployment_id)

    signed_auth_token = generate_signed_auth_token(self, system_authtoken, auth_token)

    payload = base64.b64encode(auth_token.to_json())

    return {
        'content-type': constants.APPLICATION_JSON,
        'Authorization': signed_auth_token,
        'Deployment-Id': deployment_id,
        'Deployment-Info': payload,
        'X-Requested-With': 'XMLHttpRequest',
        'x-requested-by': 'SplunkNLP'
    }

def is_valid_response(self, user, user_token, response_headers):
    if "authorization" in response_headers and 'deployment-info' in response_headers:
        rAuthToken = base64.b64decode(response_headers['authorization'])
        deployment_info = base64.b64decode(response_headers['deployment-info'])

        nlp_device_info = get_nlp_device(user, user_token)

        if '_key' in nlp_device_info:
            device_key = nlp_device_info['_key']

        kvstore = KvStore(constants.DEVICE_PUBLIC_KEYS_COLLECTION_NAME, user_token, owner="nobody")
        r, record = kvstore.get_item_by_key(device_key)
        parsed = json.loads(record)
        sender_sign_public_key = base64.b64decode(parsed['sign_public_key'])
        sign = sign_verify(self.sodium_client, sender_sign_public_key, deployment_info, rAuthToken)
        return sign
    else:
        LOGGER.info("authorization doesn't exist failed to verify response")
        return False


class ImsClient(BaseRestHandler, PersistentServerConnectionApplication):
    """
    the max timeout is 5*60=300 seconds.  Here set the value to 310 is to give some flexibility such that
    we can distinguish a slow connection and a request timeout.
    The maxWaitMillis in the backend is 300000(300 seconds) tops.
    Any connection that fails to establish within maxWaitMillis will get an 'Internal Server Error'
    """
    timeout = 310

    """
    Main class for handling NLP auth  endpoint. Subclasses the spacebridge_app
    BaseRestHandler. This multiple inheritance is an unfortunate neccesity based on the way
    Splunk searches for PersistentServerConnectionApplications
    """
    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)
        self.sodium_client = SodiumClient(LOGGER.getChild('sodium_client'))

    def get(self, request):
        LOGGER.info("action=get request={}".format(request))
        return forward_request(self, request)

    def post(self, request):
        LOGGER.info("action=post request={}".format(request))
        return forward_request(self, request)

    def put(self, request):
        LOGGER.info("action=put request={}".format(request))
        return forward_request(self, request)

    def delete(self, request):
        LOGGER.info("action=delete request={}".format(request))
        return forward_request(self, request)

def forward_request(self, request):
    method = request['method']
    path = request['path_info']
    params = request['query']
    request_headers = request['headers']

    data = None
    if 'payload' in request:
        data = request['payload']

    user = request['session']['user']
    user_token = request['session']['authtoken']
    system_authtoken = request['system_authtoken']

    resp_status = ()
    resp_body = {}
    url = None
    try:
        resp_status = (None, None)

        url = build_url(self, user, user_token, path)
        headers = get_headers(self, user, user_token, system_authtoken, request_headers)
        proxies = config.get_proxies()

        LOGGER.info("Request method={} url={} data={} params={}".format(method, url, data, params))

        if data is not None :
            data =  data.encode('utf-8')

        response = requests.request(
            method=method,
            url=url,
            data=data,
            params=params,
            headers=headers,
            proxies=proxies,
            timeout=self.timeout,
            verify=True
        )
        resp_status = (response.status_code, response.content)
        resp_body = json.loads(response.content)
        LOGGER.info("Response method={} url={} response_status={}".format(method, url, data, resp_status))
        if not is_valid_response(self, user, user_token, response.headers):
            LOGGER.info("Response sign verification failed for method={} url={} response_status={}".format(method, url, data, resp_status))
            return {
                'payload': {
                    "status": "signature verification failed"
                },
                'status': 401,
            }
        else:
            LOGGER.info("Response sign verification success for method={} url={} response_status={}".format(method, url, data, resp_status))
            return {
                'payload': resp_body,
                'status': resp_status[0],
            }

    except Exception as e:
        resp_body = {
            'url': url,
            'code': resp_status[0],
            'message': resp_status[1],
            'detail': str(e)
        }
        LOGGER.error("FORWARDING REQUEST EXCEPTION {} for response status {} resp_body {}".format(e, resp_status[0], resp_body))
        return {
                    'payload': resp_body,
                    'status': resp_status[0],
                }
