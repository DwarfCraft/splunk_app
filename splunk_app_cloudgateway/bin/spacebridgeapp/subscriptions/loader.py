import json
from collections import defaultdict

from spacebridgeapp.data.subscription_data import Subscription, SearchUpdate, SubscriptionCredential
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.subscriptions.subscription_requests import fetch_searches_for_shard
from spacebridgeapp.util.constants import SEARCH_KEY, SUBSCRIPTION_KEY, KEY, QUERY, SPACEBRIDGE_APP_NAME, NOBODY, \
    SUBSCRIPTIONS_COLLECTION_NAME, SEARCH_UPDATES_COLLECTION_NAME, SUBSCRIPTION_CREDENTIALS_COLLECTION_NAME
from spacebridgeapp.util.kvstore import build_containedin_clause
from splapp_protocol.common_pb2 import Error
from twisted.internet import defer
from twisted.web import http

LOGGER = setup_logging(SPACEBRIDGE_APP_NAME + "_subscription_loader.log",
                       "subscription_loader")


def _noop(arg):
    return arg


def _collect(arr, grouping_key):
    grouped = defaultdict(list)
    for item in arr:
        value = getattr(item, grouping_key)
        grouped[value].append(item)
    return grouped


@defer.inlineCallbacks
def _load_many(auth_header, collection, params, async_kvstore_client,
               mapper_fn=_noop, owner=NOBODY, app=SPACEBRIDGE_APP_NAME):
    """
    Queries a collection for many entries for the specified params.  It will
    marshal the result into a format you specify using mapper_fn.  The default
    behavior will return all items as python dict.
    :param auth_header: A splunk auth header used to authenticate the call
    :param collection: The name of the collection being queried
    :param params: JSON-ified query, see https://docs.splunk.com/Documentation/Splunk/8.0.2/RESTREF/RESTkvstore
    :param async_kvstore_client: An instance of the async kvstore client
    :param mapper_fn: A function that can convert a dict to something else.  Default to returning the dict.
    :param owner: The owner of the collection, defaults to nobody
    :param app: The app the collection is part of.  Default to cloud gateway.
    :return: A list of mapped entries from the collection.
    :raises: :class:`SpacebridgeApiRequestError` if the kvstore call failed
    """
    # Get all Searches so no input params
    response = yield async_kvstore_client.async_kvstore_get_request(
        collection=collection,
        params=params,
        owner=owner,
        app=app,
        auth_header=auth_header)

    if response.code != http.OK:
        error = yield response.text()
        message = "_load_many failed. status_code={}, error={}".format(response.code, error)
        LOGGER.error(message)
        raise SpacebridgeApiRequestError(message, code=Error.ERROR_API_REQUEST)

    response_json = yield response.json()
    result_list = [mapper_fn(obj) for obj in response_json]

    defer.returnValue(result_list)


@defer.inlineCallbacks
def _load_subscriptions(system_auth_header, searches, async_kvstore_client):
    if len(searches) == 0:
        defer.returnValue(defaultdict(list))

    condition = build_containedin_clause(SUBSCRIPTION_KEY, [search.key() for search in searches])

    params = {QUERY: json.dumps(condition)}
    subscriptions = yield _load_many(system_auth_header, SUBSCRIPTIONS_COLLECTION_NAME, params, async_kvstore_client,
                                     mapper_fn=Subscription.from_json)

    defer.returnValue(subscriptions)


@defer.inlineCallbacks
def _load_subscription_credentials(system_auth_header, subscriptions, async_kvstore_client):
    params = {}
    loaded_credentials = {}
    users = {subscription.user for subscription in subscriptions}

    for user in users:
        credentials = yield _load_many(system_auth_header, SUBSCRIPTION_CREDENTIALS_COLLECTION_NAME, params,
                                       async_kvstore_client,
                                       mapper_fn=SubscriptionCredential.from_json,
                                       owner=user)

        for credential in credentials:
            loaded_credentials[credential.subscription_id] = credential

    defer.returnValue(loaded_credentials)


@defer.inlineCallbacks
def _load_search_updates(system_auth_header, subscriptions, async_kvstore_client):
    if len(subscriptions) == 0:
        defer.returnValue({})

    loaded_updates = {}
    condition = build_containedin_clause(KEY, [subscription.key() for subscription in subscriptions])

    params = {QUERY: json.dumps(condition)}
    search_updates = yield _load_many(system_auth_header, SEARCH_UPDATES_COLLECTION_NAME,
                                      params, async_kvstore_client,
                                      mapper_fn=SearchUpdate.from_json)

    # One search_update per subscription
    for search_update in search_updates:
        loaded_updates[search_update.key()] = search_update

    defer.returnValue(loaded_updates)


@defer.inlineCallbacks
def load_search_bundle(system_auth_header, shard_id, async_kvstore_client):
    searches = yield fetch_searches_for_shard(system_auth_header, shard_id, async_kvstore_client)
    subscriptions_list = yield _load_subscriptions(system_auth_header, searches, async_kvstore_client)
    subscriptions_map = _collect(subscriptions_list, SUBSCRIPTION_KEY)

    subscription_credentials = yield _load_subscription_credentials(system_auth_header, subscriptions_list, async_kvstore_client)
    search_updates = yield _load_search_updates(system_auth_header, subscriptions_list, async_kvstore_client)

    defer.returnValue(SearchBundle(
        searches, subscriptions_map, subscription_credentials, search_updates
    ))


class SearchContext(object):
    def __init__(self, search, subscriptions, subscription_credentials, search_updates):
        self.search = search
        self.subscriptions = subscriptions
        self.subscription_credentials = subscription_credentials
        self.search_updates = search_updates


def _union_dependants_with_search_key(searches, search_key):
    search_keys = [search.key() for search in searches if search.parent_search_key == search_key]
    search_keys.append(search_key)
    return search_keys


def _find_all_subscriptions(subscriptions_map, search_keys):
    subscriptions = []
    for search_key in search_keys:
        search_subscriptions = subscriptions_map[search_key]
        for subscription in search_subscriptions:
            subscriptions.append(subscription)
    return subscriptions


class SearchBundle(object):
    def __init__(self, searches, subscription_map, subscription_credential_map, search_update_map):
        self.searches = searches
        self.subscriptions_map = subscription_map
        self.subscription_credentials_map = subscription_credential_map
        self.search_updates_map = search_update_map

    def to_search_context(self, search_key):
        search = next(search for search in self.searches if search.key() == search_key)

        search_keys = _union_dependants_with_search_key(self.searches, search_key)

        subscriptions = self.subscriptions_map[search_key]
        subscription_ids = {subscription.key() for subscription in subscriptions}

        # when refreshing a search we need to use credentials to start the search job
        # in the case of a root base search (meaning a search that's defined at the root of the xml and not directly
        # displayed in a panel) it has no subscribers and consequently no credentials associated with it.
        # For these cases credentials from all of the dependant searches' subscriptions are attached to the search
        # and it will use one of them.  All the roles are guaranteed to be the same by the search hash so there should
        # be no issues with permissions.
        dependant_subscriptions = _find_all_subscriptions(self.subscriptions_map, search_keys)
        dependant_subscription_ids = {subscription.key() for subscription in dependant_subscriptions}

        subscription_credentials = {subscription_id: credential for (subscription_id, credential)
                                    in self.subscription_credentials_map.items()
                                    if subscription_id in dependant_subscription_ids}

        search_updates = {key: update for (key, update)
                          in self.search_updates_map.items()
                          if key in subscription_ids}

        return SearchContext(search, subscriptions, subscription_credentials, search_updates)

