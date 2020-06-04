# Copyright 2016 Splunk Inc. All rights reserved.
# Environment configuration
# N/A
# Standard Python Libraries
import json
import sys
from os import path
from builtins import range
from future.moves.urllib.parse import quote, urlencode
from future.moves.urllib.request import Request, urlopen
from future.moves.urllib.error import HTTPError
import http.client
from utils import to_bytes

lib_dir = path.dirname(path.dirname(path.dirname(path.abspath(__file__))))  # noqa
sys.path.append(lib_dir)  # noqa
from . import BaseSplunkdServiceManager
from logging_utils import log

logger = log.getLogger()


class KVStoreManager(BaseSplunkdServiceManager):
    """
    KVStore access
    """
    # NOTE: this limit could be changed by modifying the max_rows_per_query attribute under
    # the [kvstore] stanza. Please make sure you make changes here, in the .conf
    # file, and in KVStoreMixin to user a higer/lower limit.
    KVSTORE_SINGLE_FETCH_LIMIT = 50000

    DEFAULT_BATCH_SIZE = 200

    def __init__(self, collection, server_uri,
                 session_key, app, user='nobody'):
        """
        Return KVStore Manager object
        """
        self.collection = collection
        super(KVStoreManager, self).__init__(session_key, server_uri, app, user)

    def _build_uri(self, name=None, query=None):
        """
        Create uri for kvstore request

        :param name: name after collection, usually _key
        :param query: query params
        :return: uri for kvstore request
        """
        qs = dict(output_mode='json')
        base_uri = self.base_uri()
        if query is not None:
            qs.update(query)
        if name is not None:
            return '%s/storage/collections/data/%s/%s?%s' % (
                base_uri, quote(self.collection), quote(name), urlencode(qs))
        else:
            return '%s/storage/collections/data/%s?%s' % (
                base_uri, quote(self.collection), urlencode(qs))

    def _build_req(self, method, data=None, name=None, query=None):
        """
        Build request object

        :param method: HTTP Method
        :param data: body data
        :param name: key,etc.
        :param query: query params
        :return: request object
        """
        h = {'Authorization': 'Splunk %s' % self.session_key}
        if h is not None:
            h['Content-Type'] = 'application/json'
        data_bytes = to_bytes(json.dumps(data))
        req = Request(self._build_uri(name, query=query), data_bytes, h)
        req.get_method = lambda: method
        return req

    def load(self, count=0, offset=0, fields='', sort='', params={}):
        """
        Load records with limit

        :param count: limitation
        :return: dict of records
        """
        req = self._build_req('GET', query=dict(limit=count, skip=offset, fields=fields, sort=sort, **params))
        res = urlopen(req)
        return json.loads(res.read())

    def load_all(self, batch_size=KVSTORE_SINGLE_FETCH_LIMIT, fields='', sort='', params={}):
        """
        Load all records by calling load in batch
        :return: dict of records
        """
        if not batch_size:
            raise Exception('KVStoreManager load_all() can\'t be called with batch_size=0')

        current_number = 0
        total_count = 0
        results = []
        while True:
            result = self.load(count=batch_size, offset=total_count, fields=fields,
                               sort=sort, params=params)
            results.extend(result)
            current_number = len(result)
            total_count += current_number
            if current_number < batch_size:
                break
        return results

    def get(self, key):
        """
        Get records by _key

        :param key: record's key
        :return: dict of records
        """
        req = self._build_req('GET', name=key)
        try:
            res = urlopen(req)
            return json.loads(res.read())
        except HTTPError as e:
            if e.code == http.client.NOT_FOUND:
                return None
            else:
                raise e

    def update(self, key, data):
        """
        Update record by _key

        :param key: record's key
        :param data: body data dict
        :return: result object
        """
        req = self._build_req('PUT', name=key, data=data)
        res = urlopen(req)
        return json.loads(res.read())

    def create(self, key, data):
        """
        Create record by _key

        :param key: record's key
        :param data: body data dict
        :return: result object
        """
        data.update({'_key': key})
        req = self._build_req('POST', data=data)
        res = urlopen(req)
        return json.loads(res.read())

    def upsert(self, key, data):
        """
        Insert if it doesn't exist
        Update if it exists
        """
        r = self.get(key)
        if r is None:
            return self.create(key, data)
        else:
            return self.update(key, data)

    def delete(self, key):
        """
        Delete record by _key

        :param key: record's key
        :return: void
        """
        req = self._build_req('DELETE', name=key)
        urlopen(req)

    def bulk_delete(self, query):
        """
        Bulk delete operation

        :param query: query
        :return: void
        """
        if not query:
            raise ValueError("Query is required for bulk_delete")
        try:
            req = self._build_req('DELETE', query=query)
            urlopen(req)
        except HTTPError as e:
            raise e

    def batch_save(self, data):
        """
        Perform multiple save operations in a batch
        """
        logger.debug('Batch saving data: {}'.format(data))
        if not data:
            logger.warning("Batch saving skipped: Batch is empty.")
        batches = (data[x:x + KVStoreManager.DEFAULT_BATCH_SIZE]
                   for x in range(0, len(data), KVStoreManager.DEFAULT_BATCH_SIZE))
        for batch in batches:
            try:
                req = self._build_req('POST', name='batch_save', data=batch)
                urlopen(req)
            except HTTPError as e:
                self.logger.error("Batching saving failed: %s - %s", e, e.read())
                raise e
