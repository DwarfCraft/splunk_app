import sys
import hashlib
import splunk.entity as en
import splunk.rest as rest
import json
from splunk.clilib.bundle_paths import make_splunkhome_path

sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23

from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + ".log", "nlp_utils")

def user_has_role(device_user, system_authtoken, expected_role):
    try:
        ent = en.getEntity(["authentication", "users"],
                           device_user,
                           sessionKey=system_authtoken)
        if "roles" in ent and expected_role in ent["roles"]:
            return True
    except Exception:
        LOGGER.exception('Could not get authentication/user information for user={}'.format(device_user))
    return False

def is_nlp_enabled(system_authtoken, user):
    try:
        ent = en.getEntity(["configs", "conf-nlp"],
                           "config",
                           namespace=constants.SPACEBRIDGE_APP_NAME, owner=user,
                           sessionKey=system_authtoken)
        if "enabled" in ent and ent.get('enabled') == 1:
            LOGGER.info('NLP feature flag is enabled')
            return True
    except Exception as ex:
        LOGGER.exception('Unable to get NLP configuration: {}'.format( ex))
    return False

def get_nlp_ims_api_version(system_authtoken, user):
    try:
        ent = en.getEntity(["configs", "conf-nlp"],
                           "config",
                           namespace=constants.SPACEBRIDGE_APP_NAME, owner=user,
                           sessionKey=system_authtoken)
        if "nlp_ims_server_api_version" in ent:
            return ent.get('nlp_ims_server_api_version')
    except Exception as ex:
        LOGGER.exception('Unable to get NLP configuration: {}'.format( ex))
    return None

def user_has_capability(device_user, system_authtoken, expected_capability):
    try:
        ent = en.getEntity(["authentication", "users"],
                           device_user,
                           sessionKey=system_authtoken)
        if "capabilities" in ent and expected_capability in ent["capabilities"]:
            return True
    except Exception:
        LOGGER.exception('Could not get authentication/user information for user={}'.format(device_user))
    return False

def get_mapped_user_id(deployment_id, user):
    return hashlib.sha256(deployment_id+user).hexdigest()

def get_deployment_info(user_token):
    try:
        serverResponse, serverContent = rest.simpleRequest("kvstore/deployment_info",
                                                        sessionKey=user_token, rawResult=True)
        deployment_info = json.loads(serverContent)
        return deployment_info
    except Exception:
        LOGGER.exception('Could not get deployment Info')
    return None

def check_https(url):
    return url.startswith('https://')
