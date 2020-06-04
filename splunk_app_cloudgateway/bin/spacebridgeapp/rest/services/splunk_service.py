"""
(C) 2019 Splunk Inc. All rights reserved.
"""

import json
import requests
import splunk
import splunk.rest as rest
from spacebridgeapp.util import constants
from spacebridgeapp.rest.services.kvstore_service import KVStoreCollectionAccessObject as KvStore

from spacebridgeapp.logging import setup_logging
LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_splunk_service.log", "splunk_service")


def authenticate_splunk_credentials(username, password):
    """
    Checks whether a supplied username/password pair are valid Splunk credentials. Throws an error otherwise.

    :param username: User-supplied username
    :param password: User-supplied password
    :return: None
    """
    request_url = '%s/services/auth/login' % rest.makeSplunkdUri()
    body = {
        'username': username,
        'password': password
    }
    response, _ = rest.simpleRequest(request_url, postargs=body, rawResult=True)

    if response.status == 200:
        return
    elif response.status == 401:
        exception = requests.RequestException()
        exception.msg = 'Error: Supplied username or password is incorrect'
        exception.statusCode = 401
        raise exception
    else:
        exception = requests.RequestException()
        exception.msg = 'Error: unable to authenticate client'
        exception.statusCode = response.status
        raise exception


def user_is_administrator(username, authtoken):
    """
    Checks if the given user is a Splunk admin. This is necessary for satisfying some of the UI
    feature requirements.

    :param username: Username of the user in question
    :param authtoken: Token to allow checking of user permissions
    :return: Boolean
    """
    request_url = '%s/services/authentication/users/%s' % (rest.makeSplunkdUri(), username)
    query_args = {
        'count': 0,
        'output_mode': 'json',
    }
    _, content = rest.simpleRequest(
        request_url,
        sessionKey=authtoken,
        method='GET',
        getargs=query_args,
        raiseAllErrors=True
    )
    user = json.loads(content)
    return u'admin_all_objects' in user['entry'][0]['content']['capabilities']

def has_admin_all_objects(username, authtoken):
    """
    Checks if the given user has the admin_all_objects capability

    :param username: Username of the user in question
    :param authtoken: Token to allow checking of user permissions
    :return: Boolean
    """
    request_url = '{}/services/authentication/users/{}'.format(rest.makeSplunkdUri(), username)
    query_args = {
        'count': 0,
        'output_mode': 'json',
    }
    _, content = rest.simpleRequest(
        request_url,
        sessionKey=authtoken,
        method='GET',
        getargs=query_args,
        raiseAllErrors=True
    )
    user = json.loads(content)
    return constants.ADMIN_ALL_OBJECTS in user['entry'][0]['content']['capabilities']


def get_all_users(authtoken):
    """
    Returns a list of all Splunk users viewable using the permissions of the supplied authtoken

    :param authtoken: Authorization token
    :return: List of users
    """

    request_url = '%s/services/authentication/users' % rest.makeSplunkdUri()
    query_args = {
        'count': 0,
        'output_mode': 'json',
    }
    _, content = rest.simpleRequest(
        request_url,
        sessionKey=authtoken,
        method='GET',
        getargs=query_args,
        raiseAllErrors=True
    )
    # Parse just the list of usernames from the response
    return [x['name'] for x in json.loads(content)['entry']]


def get_app_list_request(authtoken, params=None):
    """
    Returns a list of all splunk apps viewable using the permissions of the supplied authtoken

    :param authtoken: Authorization token
    :return: List of Splunk apps
    """

    request_url = '{}services/apps/local'.format(rest.makeSplunkdUri())
    params = params if params is not None else {}
    _, content = rest.simpleRequest(
        request_url,
        sessionKey=authtoken,
        method='GET',
        getargs=params,
        raiseAllErrors=True
    )
    return json.loads(content)


def get_all_mobile_users(authtoken):
    """
    Returns a list of all Splunk users with registered mobile devices

    :param authtoken: Authorization token
    :return: List of users
    """
    kvstore = KvStore(constants.REGISTERED_USERS_COLLECTION_NAME, authtoken)
    _, content = kvstore.get_collection_keys()
    registered_user_records = json.loads(content)
    return [registered_user_record[u'_key'] for registered_user_record in registered_user_records]


def get_devices_for_user(user, authtoken):
    """
    Gets devices belonging to a user from the kvstore
    :param user: Username to retrieve devices for
    :param authtoken: Authorization token to supply to the kvstore interface
    :return: List of devices
    """
    kvstore = KvStore(constants.REGISTERED_DEVICES_COLLECTION_NAME, authtoken, owner=user)
    _, devices_record = kvstore.get_items_by_query(query={}, sort="device_name")
    LOGGER.debug("user={}, devices={}".format(user, devices_record))
    return json.loads(devices_record)


def user_has_registered_devices(user, authtoken):
    """
    Returns true if a user has at least one registered device
    :param user: Username to check
    :param authtoken: Authorization token to supply to the kvstore interface
    :return: Boolean result
    """
    return len(get_devices_for_user(user, authtoken)) > 0


def get_splunk_auth_type(authtoken):
    """
    Returns authentication type for Splunk instance (Splunk, LDAP, or SAML)
    :return: String
    """
    LOGGER.debug("Getting Splunk authentication type")
    query_args = {
        'output_mode': 'json',
    }
    request_url = "{}services/properties/authentication/authentication/authType".format(rest.makeSplunkdUri())
    _, content = rest.simpleRequest(
        request_url,
        sessionKey=authtoken,
        method='GET',
        getargs=query_args,
        raiseAllErrors=True
    )
    return content


def create_sensitive_data(session_key, key, data):
    """
    :param session_key: A raw system auth token
    :param key: the string key to fetch the sensitive data for
    :param data: String data representing the secret
    :return:
    """
    LOGGER.debug("Updating sensitive data, key={}".format(key))
    base_uri = rest.makeSplunkdUri()
    uri = '{}servicesNS/nobody/{}/storage/passwords'.format(base_uri, constants.SPACEBRIDGE_APP_NAME)

    form_data = {
        constants.NAME: key,
        constants.PASSWORD: data
    }

    return _mutate_sensitive_data(session_key, uri, form_data)


def update_sensitive_data(session_key, key, data):
    """
    :param session_key: A raw system auth token
    :param key: the string key to fetch the sensitive data for
    :param data: String data representing the secret
    :return:
    """
    LOGGER.debug("Updating sensitive data, key={}".format(key))
    base_uri = rest.makeSplunkdUri()
    uri = '{}servicesNS/nobody/{}/storage/passwords/{}'.format(base_uri, constants.SPACEBRIDGE_APP_NAME, key)

    form_data = {
        constants.PASSWORD: data
    }

    return _mutate_sensitive_data(session_key, uri, form_data)


def update_or_create_sensitive_data(session_key, key, data):
    """
    Method that tries to update, and if that fails, tries to create
    an entry in storage/passwords.
    Function inspiration from:
    https://docs.djangoproject.com/en/2.2/ref/models/querysets/#update-or-create
    :param session_key: A raw system auth token
    :param key: the string key to fetch the sensitive data for
    :param data: String data representing the secret
    :return [response, created]: Response + true if data created else false
    """
    try:
        return [update_sensitive_data(session_key, key, data), False]
    except splunk.ResourceNotFound:
        return [create_sensitive_data(session_key, key, data), True]


def _mutate_sensitive_data(session_key, uri, form_data):
    """
    :param session_key: A raw system auth token
    :param uri: The uri to act on
    :param form_data: a dict containing the key 'password' and optionally 'name' if you are creating
    :return:
    """
    params = {
        'output_mode': 'json'
    }

    rest.simpleRequest(
        uri,
        sessionKey=session_key,
        getargs=params,
        postargs=form_data,
        method='POST',
        raiseAllErrors=True
    )


def fetch_sensitive_data(session_key, key):
    """
    :param session_key: A raw system auth token
    :param key: the string key to fetch the sensitive data for
    :return: string representation of the secret
    """
    LOGGER.debug("retrieving sensitive data, key={}".format(key))
    base_uri = rest.makeSplunkdUri()
    uri = '{}servicesNS/nobody/{}/storage/passwords/{}'.format(base_uri, constants.SPACEBRIDGE_APP_NAME, key)

    params = {
        'output_mode': 'json'
    }

    _, content = rest.simpleRequest(
        uri,
        sessionKey=session_key,
        getargs=params,
        method='GET',
        raiseAllErrors=True
    )

    parsed = json.loads(content)
    clear_password = parsed['entry'][0]['content']['clear_password']
    return clear_password
