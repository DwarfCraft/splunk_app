from splunk import rest as rest

import json
import requests
import treq
from cloudgateway.private.clients.async_client import AsyncClient
from twisted.internet import defer
from twisted.web import http
from cloudgateway.auth import SimpleUserCredentials, UserAuthCredentials
from cloudgateway.private.util import constants

class SplunkAuthHeader(object):
    """
    Wrapper for a splunk session token. Returns a splunk auth header when stringified
    to be used on HTTP requests to Splunk's REST apis
    """
    def __init__(self, session_token):
        self.session_token = session_token

    def __repr__(self):
        return 'Splunk {0}'.format(self.session_token)

    @defer.inlineCallbacks
    def validate(self, async_splunk_client):
        """
        Check if this auth header is valid or not against Splunk
        """
        response = yield async_splunk_client.async_get_current_context(auth_header=self)
        if response.code == http.OK:
            defer.returnValue(True)
        defer.returnValue(False)


class SplunkBasicCredentials(SimpleUserCredentials):
    """Basic username and password credentials wrapper which gets validated with Splunk
    """

    def validate(self):
        """validate username and password with Splunk
        """
        authenticate_splunk_credentials(self.username, self.password)


class SplunkJWTCredentials(UserAuthCredentials):
    """
    Credentials interface for Splunk JWT Tokens
    """

    def __init__(self, username, password=None):
        self.username = username
        self.password = password
        self.token = None

    def load_jwt_token(self, system_auth, audience=constants.CLOUDGATEWAY):
        if self.password:
            self.fetch_jwt_token_from_basic_creds(self.username, self.password, audience)
        else:
            self.fetch_jwt_token_from_session_key(self.username, system_auth, audience)

    def get_username(self):
        return self.username

    def validate(self):
        pass

    def jwt_token_url(self):
        return '{}services/authorization/tokens?output_mode=json'.format(rest.makeSplunkdUri())

    def jwt_token_data(self, username, audience):
        return {
            "name": username,
            "not_before": "+0d",
            "audience": audience
        }

    def fetch_jwt_token_from_basic_creds(self, username, password, audience):
        """
        Creates a new JWT token for the given user

        :param username: User-supplied username
        :param password: User-supplied password
        :param audience: User-supplied purpose of this token
        :return: JWT token for given user
        """
        url = self.jwt_token_url()
        data = self.jwt_token_data(username, audience)

        headers = {constants.HEADER_CONTENT_TYPE: constants.APPLICATION_JSON}

        r = requests.post(url, data=data, verify=False, auth=(username,password), headers=headers)

        if r.status_code != http.CREATED:
            raise Exception('Exception creating JWT token with code={}, message={}'.format(r.status_code, r.text))

        self.token = r.json()['entry'][0]['content']['token']

    def fetch_jwt_token_from_session_key(self, username, system_auth_header, audience):
        """
        Creates a new JWT token for the given user

        :param username: User-supplied username
        :param session_key: Session key supplied to user from Splunk
        :param audience: User-supplied purpose of this token
        :return: JWT token for given user
        """
        url = self.jwt_token_url()
        data = self.jwt_token_data(username, audience)

        headers = {
            constants.HEADER_CONTENT_TYPE: constants.APPLICATION_JSON,
            constants.HEADER_AUTHORIZATION: '{}'.format(system_auth_header),
            constants.HEADER_CONTENT_TYPE: constants.CONTENT_TYPE_FORM_ENCODED
        }

        r = requests.post(url, data=data, verify=False, headers=headers)

        if r.status_code != http.CREATED:
            raise Exception('Exception creating JWT token with code={}, message={}'.format(r.status_code, r.text))

        self.token = r.json()['entry'][0]['content']['token']


    def get_credentials(self):
        return json.dumps({
            'username': self.username,
            'token': self.token,
            'type': constants.JWT_TOKEN_TYPE
        })

class SplunkJWTMDMCredentials(SplunkJWTCredentials):

    def __init__(self, username, password=None):
        self.username = username
        self.password = password
        self.token = None
        self.async_client = AsyncClient()

    @defer.inlineCallbacks
    def load_jwt_token(self, system_auth, audience=constants.CLOUDGATEWAY):
        if self.password:
            self.token = yield self.fetch_jwt_token_from_basic_creds(self.username, self.password, audience)
        else:
            self.token = yield self.fetch_jwt_token_from_session_key(self.username, system_auth, audience)

    @defer.inlineCallbacks
    def fetch_jwt_token_from_basic_creds(self, username, password, audience):
        """
        Creates a new JWT token for the given user

        :param username: User-supplied username
        :param password: User-supplied password
        :param audience: User-supplied purpose of this token
        :return: JWT token for given user
        """

        url = self.jwt_token_url()
        data = self.jwt_token_data(username, audience)

        headers = {constants.HEADER_CONTENT_TYPE: constants.APPLICATION_JSON}

        r = yield self.async_client.async_post_request(url, None, auth=(username, password), data=data, headers=headers)

        if r.code != http.CREATED:
            text = yield r.text()
            raise Exception('Exception creating JWT token with code={}, message={}'.format(r.code, text))

        response = yield r.json()
        defer.returnValue(response['entry'][0]['content']['token'])

    @defer.inlineCallbacks
    def fetch_jwt_token_from_session_key(self, username, system_auth_header, audience):
        """
        Creates a new JWT token for the given user

        :param username: User-supplied username
        :param session_key: Session key supplied to user from Splunk
        :param audience: User-supplied purpose of this token
        :return: JWT token for given user
        """
        url = self.jwt_token_url()
        data = self.jwt_token_data(username, audience)

        headers = {
            constants.HEADER_CONTENT_TYPE: constants.APPLICATION_JSON,
            constants.HEADER_AUTHORIZATION: '{}'.format(system_auth_header),
            constants.HEADER_CONTENT_TYPE: constants.CONTENT_TYPE_FORM_ENCODED
        }

        r = yield self.async_client.async_post_request(url, None, data=data, headers=headers)

        if r.code != http.CREATED:
            text = yield r.text()
            raise Exception('Exception creating JWT token with code={}, message={}'.format(r.code, text))

        response = yield r.json()
        defer.returnValue(response['entry'][0]['content']['token'])


def authenticate_splunk_credentials(username, password):
    """
    Checks whether a supplied username/password pair are valid Splunk credentials. Throws an error otherwise.

    :param username: User-supplied username
    :param password: User-supplied password
    :return: None
    """
    request_url = '{}/services/auth/login'.format(rest.makeSplunkdUri())
    body = {
        'username': username,
        'password': password
    }
    response, c = rest.simpleRequest(request_url, postargs=body, rawResult=True)
    exception = requests.RequestException()
    exception.statusCode = response.status

    if response.status == 200:
        return

    elif response.status == 401:
        exception.msg = 'Error: Supplied username or password is incorrect'
    else:
        exception.msg = 'Error: unable to authenticate client'

    raise exception

