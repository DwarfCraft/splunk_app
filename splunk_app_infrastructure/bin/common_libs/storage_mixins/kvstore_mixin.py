import json
try:
    import http.client as httplib
except ImportError:
    import httplib

from .base_mixin import AbstractBaseStorageMixin
from rest_handler.session import session, authtoken_required
from splunk import getDefault
from splunklib.binding import HTTPError
from splunklib.client import Service

# NOTE: this limit could be changed by modifying the max_rows_per_query attribute under
# the [kvstore] stanza. Please make sure you make changes here, in the .conf
# file, and in KVStoreManager to user a higer/lower limit.
KVSTORE_SINGLE_FETCH_LIMIT = 50000


class KVStoreMixin(AbstractBaseStorageMixin):

    @classmethod
    def store(cls):
        svc = Service(
            port=getDefault('port'),
            token=session['authtoken'],
            app=cls.app_name(),
            owner='nobody',
        )
        store = svc.kvstore[cls.storage_name()]
        return store

    @classmethod
    @authtoken_required
    def storage_get(cls, key):
        store = cls.store()
        try:
            data = store.data.query_by_id(key)
        except HTTPError as e:
            if e.status == httplib.NOT_FOUND:
                return None
            else:
                raise e
        return data

    @classmethod
    @authtoken_required
    def storage_load(cls, limit, skip, sort_keys_and_orders, fields, query=None):
        query_str = json.dumps(query) if query else ''
        limit, skip = int(limit), int(skip)
        sort = ','.join([
            '{}:{}'.format(key, 1 if order == 'asc' else -1) for key, order in sort_keys_and_orders
        ])
        if limit == 0 or limit > KVSTORE_SINGLE_FETCH_LIMIT:
            data = cls._paged_load(limit, skip, sort, fields, query_str)
        else:
            data = cls._regular_load(limit, skip, sort, fields, query_str)
        return data

    @classmethod
    def _regular_load(cls, limit, skip, sort, fields, query):
        store = cls.store()
        data = store.data.query(limit=limit, skip=skip, sort=sort, fields=fields, query=query)
        return data

    @classmethod
    def _paged_load(cls, limit, skip, sort, fields, query):
        store = cls.store()
        cur_offset = skip
        data = []
        while True:
            paged_data = store.data.query(
                limit=KVSTORE_SINGLE_FETCH_LIMIT,
                skip=cur_offset,
                sort=sort,
                fields=fields,
                query=query
            )
            data.extend(paged_data)
            cur_offset += KVSTORE_SINGLE_FETCH_LIMIT
            # if user is requesting to fetch all rows and last fetch has less than the max number
            # of rows allowed (meaning no more fetch is needed)
            if limit == 0 and len(paged_data) < KVSTORE_SINGLE_FETCH_LIMIT:
                break
            # if the number of rows requested has been fully fetched
            if limit != 0 and cur_offset >= skip + limit:
                break
        return data

    @classmethod
    @authtoken_required
    def storage_bulk_delete(cls, delete_query):
        store = cls.store()
        query_str = json.dumps(delete_query) if delete_query else ''
        resp = store.data.delete(query=query_str)
        return resp

    @classmethod
    @authtoken_required
    def storage_create(cls, data):
        if isinstance(data, dict):
            data = json.dumps(data)
        store = cls.store()
        resp = store.data.insert(data)
        key = resp['_key']
        rtval = store.data.query_by_id(key)
        return rtval

    @classmethod
    @authtoken_required
    def storage_save(cls, key, data):
        if isinstance(data, dict):
            data = json.dumps(data)
        store = cls.store()
        store.data.update(key, data)

    @classmethod
    @authtoken_required
    def storage_bulk_save(cls, data):
        store = cls.store()
        store.data.batch_save(*data)
