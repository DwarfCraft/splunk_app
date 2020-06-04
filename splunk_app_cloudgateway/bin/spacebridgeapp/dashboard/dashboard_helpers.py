"""
(C) 2019 Splunk Inc. All rights reserved.

Module for dashboard helper function
"""

import re
import hashlib

DASHBOARD_ID_URL_REGEX = r'^https?://.+/servicesNS/(?P<user>[a-zA-Z0-9-_.]+)/' \
                     r'(?P<app_name>[a-zA-Z0-9-_.]+)/data/ui/views/(?P<dashboard_name>[a-zA-Z0-9-_.]+)$'
DASHBOARD_ID_URL_MATCHER = re.compile(DASHBOARD_ID_URL_REGEX)
FIELD_REGEX = r'[a-zA-Z0-9-_.]+'
FIELD_MATCHER = re.compile(FIELD_REGEX)

def generate_dashboard_id(owner, app_name, dashboard_name):
    """
    Helper to generate dashboard_id
    :param owner:
    :param app_name:
    :param dashboard_name:
    :return:
    """
    return '%s/%s/%s' % (owner, app_name, dashboard_name)


def shorten_dashboard_id_from_url(dashboard_id_url):
    """
    Helper to generate compact dashboard_id from dashboard_id url
    :param dashboard_id_url:
    :return:
    """
    m = DASHBOARD_ID_URL_MATCHER.search(dashboard_id_url)
    if m is not None:
        return "%s/%s/%s" % (m.group('user'), m.group('app_name'), m.group('dashboard_name'))
    # Return full url if unable to shorten
    return dashboard_id_url


def parse_dashboard_id(dashboard_id):
    """
    Helper to parse a dashboard_id either a compact or url version into its
    individual parts 'user', 'app_name', 'dashboard_name'
    :param dashboard_id:
    :return:
    """
    m = DASHBOARD_ID_URL_MATCHER.search(dashboard_id)
    if m is not None:
        return m.group('user'), m.group('app_name'), m.group('dashboard_name')
    else:
        data_list = dashboard_id.split('/')
        if len(data_list) == 3 and all(FIELD_MATCHER.match(data) is not None for data in data_list):
            return data_list[0], data_list[1], data_list[2]
    return '', '', dashboard_id


def generate_visualization_id(earliest=None, latest=None, query=None, refresh=None, refresh_type=None,
                              sample_ratio=None, row_index=0, panel_index=0, ref=None):
    """
    Helper to generate a hash to represent the visualization id.
    :param earliest:
    :param latest:
    :param query:
    :param refresh:
    :param refresh_type:
    :param sample_ratio:
    :param row_index:
    :param ref:
    :param panel_index:
    :return:
    """
    values_to_hash = [earliest if earliest is not None else '',
                      latest if latest is not None else '',
                      query if query is not None else '']

    if refresh:
        values_to_hash.append(str(refresh))

    if refresh_type:
        values_to_hash.append(str(refresh_type))

    if sample_ratio:
        values_to_hash.append(str(sample_ratio))

    if ref and len(ref) > 0:
        values_to_hash.append(ref)

    string_to_hash = ','.join(values_to_hash).encode('utf-8')

    hash_object = hashlib.sha256(string_to_hash)
    return '%s/%d/%d' % (hash_object.hexdigest(), row_index, panel_index)


def convert_id_to_query(dashboard_id):
    owner, app_name, dashboard_name = parse_dashboard_id(dashboard_id)
    # Don't include owner in filter because of MSB-771
    values = []

    if app_name:
        values.append('eai:appName="{}"'.format(app_name))

    if dashboard_name:
        values.append('name="{}"'.format(dashboard_name))

    return '({})'.format(' AND '.join(values))


def generate_search_str(app_names, dashboard_ids, current_user):
    """
        Helper to generate search string for dashboard list request query
        :param app_names:
        :param dashboard_ids:
        :param current_user:
        :return:
    """
    dashboard_id_query = ''
    app_name_query = ''

    # if app_names specified add to search filter
    if app_names:
        query = ['eai:acl.app="{}"'.format(app_name) for app_name in app_names]
        app_name_query = '({}) AND '.format(' OR '.join(query))

    # If a set of dashboard_ids is given, add search logic to search_str
    if dashboard_ids:
        query = [convert_id_to_query(dashboard_id) for dashboard_id in dashboard_ids]
        separator = ' OR '
        dashboard_id_query = ' AND ({})'.format(separator.join(query))

    # This is the current search string passed by API from search and reporting to fetch dashboards
    search_str = '((isDashboard=1 AND isVisible=1 AND (rootNode="form" OR rootNode="dashboard")) ' \
                 'AND ((eai:acl.sharing="global") OR ({app_names_query}((eai:acl.sharing="app") ' \
                 'OR (eai:acl.sharing="user" AND eai:acl.owner="{user}")))){dashboard_id_query})'\
        .format(app_names_query=app_name_query, user=current_user, dashboard_id_query=dashboard_id_query)
    return search_str


def to_dashboard_key(dashboard_id):
    """
    Helper method to return a key for
    :param dashboard_id:
    :return:
    """
    if not dashboard_id:
        return None

    app_and_name = dashboard_id.split("/")[1:]
    return "/".join(app_and_name)

def get_dashboard_input_tokens(dashboard_definition):
    """
    Helper method to get all input tokens from a dashboard definition (dahsboard level + panel level)
    :param dashboard_definition: DashboardDefinition()
    :return: list of InputToken()
    """
    input_tokens = []
    input_tokens.extend(dashboard_definition.input_tokens)
    for row in dashboard_definition.list_rows:
        for panel in row.list_dashboard_panels:
            input_tokens.extend(panel.input_tokens)
    return input_tokens
