# Copyright 2016 Splunk Inc. All rights reserved.
# Environment configuration
# N/A
# Standard Python Libraries
import em_path_inject  # noqa
import base64
import json
import socket
from collections import namedtuple
import time
from distutils.util import strtobool
# Third-Party Libraries
from splunk import getReleaseVersion
import splunk.clilib.cli_common as comm
import splunk.rest
from solnlib.packages.splunklib.binding import HTTPError
from solnlib.server_info import ServerInfo
from solnlib.utils import retry
from splunk import getDefault
from utils import to_bytes, to_str
from utils.i18n_py23 import _
# Custom Libraries
from em_exceptions import ArgValidationException
from logging_utils.instrument import Instrument
from logging_utils import log

try:
    basestring
except NameError:
    basestring = str


# The new default search behavior is to NOT ignore case
MONGODB_RESPECT_CASE = {"ignoreCase": False}
# em_rest_groups_impl overrides default behavior (it always ignores case)
MONGODB_IGNORE_CASE = {"ignoreCase": True}


class KVStoreNotReadyException(Exception):
    pass


def merge_dicts(*dicts):
    """
    Merge two dict

    :param *dicts: list of dicts
    :return: dict after being merged
    """
    res = dict()
    for d in dicts:
        res.update(d)
    return res


def get_server_uri():
    """
    :return: current server uri
    """
    return splunk.rest.makeSplunkdUri().rstrip('/')


def is_splunk_cloud(url):
    """
    check whether url is for splunkcloud

    :param url: url to check
    :return: boolean
    """
    if url:
        return url.endswith('cloud.splunk.com') or url.endswith('splunkcloud.com')
    return False


def get_splunkweb_fqdn():
    """
    :return: current server fqdn
    """
    fqdn = socket.getfqdn()
    serverUri = comm.getWebUri()
    return serverUri.replace('127.0.0.1', fqdn)


def get_key_from_dims(dims=None):
    """
    Receive a dictionary, return an unique key

    :param dims: dictionary of dimension
    :return: base64 encoded key
    """
    if dims is None:
        return ''
    return to_str(base64.b64encode(to_bytes(json.dumps(dims, sort_keys=True))))


def always_list(v):
    """
    Return a list even it's a value
    """
    return v if isinstance(v, list) else [v]


def _get_splunk_version():
    return int(getReleaseVersion().split('.')[0])


def ignore_case():
    return _get_splunk_version() < 8


def _get_default_options():
    return MONGODB_IGNORE_CASE if ignore_case() else MONGODB_RESPECT_CASE


def convert_query_params_to_mongoDB_query(query=None, options=None):
    """
    Converts query params to mongoDB format
    :param query: dict or string, the query containing filter to be converted to mongo format
    :param options: dict or string, options for mongo search (example: is search case sensitive or not)
    :return: dict or nothing
    """
    if not query:
        return {}
    if isinstance(query, str):
        query = json.loads(query)
    try:
        return build_mongodb_query(query, options=options)
    # Throws ArgalidationException when we provide invalid dict for mongodb query, a cleaner
    # exception message than default ValueError returned
    except ValueError:
        raise ArgValidationException(_('Invalid dict supplied as part of query!'))


def get_list_of_admin_managedby(query, app_name):
    """
    Converts UI query to a list of entities
    that are preceded by 'alert.managedBy:'
    :param query query string from UI
    :return
    """
    if not query:
        return []
    else:
        try:
            type_ids = []
            if type(query) is dict:
                type_ids = query.get('_key', [])
            # Getting a delete all call here, so take all entities
            else:
                type_ids = [entity_type.get('_key') for entity_type in query]
            return ['alert.managedBy="%s:%s"' % (app_name, type_id) for type_id in type_ids]
        except ValueError:
            raise ArgValidationException(_('Invalid JSON supplied as part of query!'))


def get_locale_specific_display_names(dimension_display_names, locale='en-us', collector_name=None):
    """
    Convert the collector config display name items to flattened locale-specific items
    """
    display_names = []
    for dimension_display_name in dimension_display_names:
        dimension = list(dimension_display_name.keys())[0]
        display_name = {}
        if collector_name is not None:
            display_name['collector_name'] = collector_name
        display_name['dimension_name'] = dimension
        display_name['display_name'] = dimension_display_name[dimension].get(locale, dimension)
        display_names.append(display_name)
    return display_names


def build_mongodb_query(filters, options=None):
    """
    Ex1: for a input  {"title": ["a*"]}
    this function would return  {"title": {"$regex": "a*", , "$options": "i"}}

    Ex2: for a input {"title": ["a*", "b"]}
    returns:  {"$or": [{"title": {"$regex": "a*", "$options": "i"}}, {"title": {"$regex": "b", , "$options": "i"}} ]}

    Ex3: for a input {"title": ["a*", "b"], "os": ["windows"]}
    returns:  {"$and": [
        {"$or": [{"title": {"$regex": "a*", "$options": "i"}},  {"$regex": "b", , "$options": "i"}} ]},
        {"os":  {"$regex": "windows", , "$options": "i"}}}
    ]}

    NOTE: This code needs to be updated when  https://jira.splunk.com/browse/PBL-9076 is implemented.

    :param filters dictionary, filters object passed by the UI
    :param options dictionary of supported options
    :return mongoDB format query dictionary:
    """
    # if filters is empty object return as no query constructions required
    if not bool(filters):
        return filters

    if not options:
        options = _get_default_options()
    elif isinstance(options, str):
        options = json.loads(options)
    elif not isinstance(options, dict):
        raise ArgValidationException(_('When provided, options must be string or dict'))

    mongo_options = _construct_mongo_options(options)

    # if filter is not a dict or options if passed in is not a dict a error will be thrown
    if not isinstance(filters, dict):
        raise ArgValidationException(_('Filter must be a dict'))

    sub_queries = [_construct_query_for(key, value, mongo_options) for key, value in filters.items()]

    # if number of sub-queries is 1 return else wrap it around a "$and"
    return sub_queries[0] if len(sub_queries) == 1 else {"$and": sub_queries}


def _construct_query_for(key, value, options):
    """
    If values is a list it would return
        {"$or": [{"key":"a"}, {"key": "b"}]}

    else it would return
        {"key": "value"}
    :return:
    """
    if not (isinstance(value, list) or isinstance(value, basestring)):
        raise ArgValidationException(_('Value needs to be a string or list'))

    item = {}
    if isinstance(value, list):
        item['$or'] = [{key: get_regex_search_string(v, options)} for v in value]
    else:
        item[key] = get_regex_search_string(value, options)
    return item


def get_regex_search_string(value, options):
    """
    - It is not a good idea to use regex for all searches , instead we should start storing
    data in lowercase always.
    """
    if '*' in value:
        # need to do this to to handle a filter like host:m*, .* will allow chars after the match
        value = value.replace('*', '.*')

    return {"$regex": '^%s$' % value, "$options": options}


def _construct_mongo_options(options):
    """
    :param options dictionary of options for regex:
    :return a string for mongo query:
    """
    options_str = ""
    if "ignoreCase" in options and options['ignoreCase']:
        options_str += "i"

    return options_str


def negate_special_mongo_query(query_dict):
    """
    Turn a Mongo query in the form of {"$or": [ regex_expr1, regex_expr2, ... ]}
    to its negation: {"$and": [ not_regex_expr1, not_regex_expr2, ...]}
    :param query_dict: Mongo query string
    :return: dict

    $NOT is not allowed in Mongo for complex expressions
        https://jira.mongodb.org/browse/SERVER-10708
    $NOR is not allowed in Splunk for unknown reasons
        main/src/statestore/MongoStorageProvider.cpp
    Hence this weird hack with negating the Regex.
    """
    query_dict["$and"] = query_dict.pop("$or")
    for expression in query_dict["$and"]:
        orig_regex = expression["_key"]["$regex"]
        expression["_key"]["$regex"] = "^(?!%s).*$" % orig_regex[1:-1]
    return query_dict


def Enum(**kwargs):
    """
    :param key=value pairs
    :return a namedtuple
    Sample usage:
    Numbers = Enum(One=1, Two=2)
    Numbers.One -> 1
    Numbers.Two -> 2
    for number in Numbers:
        number
    -> 2
    -> 1
    Note: The order is not guaranteed if you interate through Enum
    """
    return namedtuple('Enum', list(kwargs.keys()))(*list(kwargs.values()))


def string_to_list(string, sep=','):
    """
    Convert a 'sep' separated string into a list
    :param sep: separator, default to ','
    :param string: string to be converted
    :return: list
    """
    return [el.strip() for el in string.split(sep)]


def is_url_valid(session_key, url):
    """
    Check if url is valid
    :param session_key
    :param url: string of url
    :return: boolean
    """
    try:
        response, content = splunk.rest.simpleRequest(url, method='GET', sessionKey=session_key)
        if response.status == 200 or response.status == 400:
            return True
        else:
            return False
    except Exception:
        return False


@Instrument()
def modular_input_should_run(session_key, logger=None):
    """
    Determine if a modular input should run or not.
    Run if and only if:
    1. Node is not a SHC member
    2. Node is an SHC member and is Captain
    @return True if condition satisfies, False otherwise
    """
    if any([not isinstance(session_key, basestring), isinstance(session_key, basestring) and not session_key.strip()]):
        raise ValueError('Invalid session key')

    info = ServerInfo(session_key, port=getDefault('port'))
    logger = log.getLogger() if not logger else logger

    if not info.is_shc_member():
        return True

    timeout = 300  # 5 minutes
    while timeout > 0:
        try:
            # captain election can take time on a rolling restart.
            if info.is_captain_ready():
                break
        except HTTPError as e:
            if e.status == 503:
                logger.warning(
                    'SHC may be initializing on node `%s`. Captain is not ready. Will try again.', info.server_name)
            else:
                logger.exception('Unexpected exception on node `%s`', info.server_name)
                raise
        time.sleep(5)
        timeout -= 5

    # we can fairly be certain that even after 5 minutes if `is_captain_ready`
    # is false, there is a problem
    if not info.is_captain_ready():
        raise Exception(('Error. Captain is not ready even after 5 minutes. node=`%s`.'), info.server_name)

    return info.is_captain()


def convert_to_bool(val):
    try:
        if isinstance(val, bool):
            return val
        if isinstance(val, basestring):
            return bool(strtobool(val))
        return bool(val)
    except Exception:
        raise ValueError('cannot convert %r to bool' % val)
    return False


@retry(retries=10, exceptions=[KVStoreNotReadyException, HTTPError])
def check_kvstore_readiness(session_key):
    # Get a random entry from the KVstore
    resp, content = splunk.rest.simpleRequest('kvstore/status', method='GET',
                                              sessionKey=session_key,
                                              getargs={'output_mode': 'json'})
    parsed_content = json.loads(content)
    status = parsed_content['entry'][0]['content']['current']['status']
    if status != 'ready':
        raise KVStoreNotReadyException('KVstore is not ready - last checked status: "%s"' % status)
