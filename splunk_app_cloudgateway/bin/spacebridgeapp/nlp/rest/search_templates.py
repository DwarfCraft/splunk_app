"""
(C) 2019 Splunk Inc. All rights reserved.

REST endpoint handler for the Spacebridge registration process, including
both the AuthenticationQueryRequest and the DevicePairingConfirmationRequest
"""

import sys
import json
import re
import urllib
import splunk.rest as rest
from splunk.persistconn.application import PersistentServerConnectionApplication
from splunk.clilib.bundle_paths import make_splunkhome_path


sys.path.append(make_splunkhome_path(['etc', 'apps', 'splunk_app_cloudgateway', 'bin']))
from spacebridgeapp.util import py23


from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.rest.base_endpoint import BaseRestHandler
import spacebridgeapp.dashboard.parse_data as parse

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + ".log", "rest_nlp_saved_search_spl")


class SearchTemplatesHandler(BaseRestHandler, PersistentServerConnectionApplication):
    """
    Main class for handling REST Registration endpoint. Subclasses the spacebridge_app
    BaseRestHandler. This multiple inheritance is an unfortunate neccesity based on the way
    Splunk searches for PersistentServerConnectionApplications
    """

    def __init__(self, command_line, command_arg):
        BaseRestHandler.__init__(self)

    def get(self, request):
        user = request['session']['user']
        user_token = request['session']['authtoken']

        return handle(user, user_token)


def handle(user, user_token):
    """
    Handler for the initial AuthenticationQueryRequest call. This function:
        1. Makes the AuthenticationQueryRequest request to the server
        2. Checks if app_type has been disabled
        3. Stores a temporary record in the kvstore

    :param auth_code: User-entered authorization code to be returned to Spacebridge
    :param device_name: Name of the new device
    :return: Confirmation code to be displayed to user, and id of temporary kvstore record to be returned later
    """

    LOGGER.info('Received request for show spl by user=%s' % user)

    saved_search_list = get_saved_search_list(user_token)
    dashboard_list = get_dashboards_list(user_token)
    LOGGER.info('all response saved_search_lists={}'.format(saved_search_list))
    LOGGER.info('all response dashboard_list={}'.format(dashboard_list))
    return {
        'payload': saved_search_list + dashboard_list,
        'status': 200,
    }


def get_saved_search_list(user_token):
    search_str = 'NOT ((is_scheduled=1 AND (alert_type!=always OR alert.track=1 OR (dispatch.earliest_time="rt*" AND dispatch.latest_time="rt*" AND actions="*" AND actions!="")))) AND ((eai:acl.sharing="user" AND eai:acl.owner="admin") OR (eai:acl.sharing!="user")) AND is_visible=1'
    encoded_search_str = urllib.quote(search_str)
    server_response, server_content = rest.simpleRequest("/servicesNS/-/search/saved/searches?output_mode=json&offset=0&count=0&search={}".format(encoded_search_str), sessionKey=user_token)
    
    response_json = json.loads(server_content)
    entry_list = response_json.get('entry')

    saved_search_list = []
    # populate saved searches
    for entry in entry_list:
        if entry is not None and isinstance(entry, dict):
            template_type = "SavedSearch"
            name = parse.get_string(entry.get('name'))
            content = entry.get('content', {})
            
            spl = parse.get_string(content.get('search')) if 'search' in content else ""
            params = extract_params_from_spl(spl)

            saved_search_list.append({
                "type": template_type,
                "label": name,
                "reference": name,
                "spl": spl,
                "appName": get_app_name(entry),
                "params": params
            })

    return saved_search_list

def get_dashboards_list(user_token):
    search_str = '((isDashboard=1 AND isVisible=1) AND ((eai:acl.sharing="user" AND eai:acl.owner="admin") OR (eai:acl.sharing!="user")))'
    encoded_search_str = urllib.quote(search_str)
    server_response, server_content = rest.simpleRequest("/servicesNS/-/search/data/ui/views?output_mode=json&offset=0&count=0&search={}".format(encoded_search_str), sessionKey=user_token)

    response_json = json.loads(server_content)
    entry_list = response_json.get('entry')

    dashboard_list = []
    # populate dashboards
    for entry in entry_list:
        LOGGER.info('all response entry={}'.format(entry))
        if entry is not None and isinstance(entry, dict):
            template_type = "Dashboard"
            
            content = entry.get('content', {})

            label = parse.get_string(content.get('label')) if "label" in content else ""
               
            dashboard_id = parse.get_string(entry.get('id'))
            
            dashboard_list.append({
                "type": template_type,
                "label": label,
                "reference": dashboard_id,
                "appName": get_app_name(entry)
            })

    return dashboard_list
    
def extract_params_from_spl(spl):
    found = re.findall('\$(.+?)\$', spl)
    if not found:
        LOGGER.debug("No Params found")

    return found

def get_app_name(entry):
    acl = entry.get("acl")
    app_name = ""
    if acl is not None:
        app_name = parse.get_string(acl.get('app'))
        app_name = "search and reporting" if app_name == 'search' else app_name
    return app_name
