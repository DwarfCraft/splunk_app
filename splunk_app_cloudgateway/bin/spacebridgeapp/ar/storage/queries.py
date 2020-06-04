"""
(C) 2020 Splunk Inc. All rights reserved.

Utilities for building common KV store queries
"""
import json

from spacebridgeapp.util.constants import OR_OPERATOR, KEY


def get_query_matching_keys(keys):
    return get_query_matching_field(KEY, keys)


def get_query_matching_field(field_name, values):
    if not values:
        raise ValueError('"values" must be non-None and nonempty.')
    if len(values) == 1:
        val = next(iter(values))  # values may be a set or some other non-list iterable
        return json.dumps({field_name: val})
    return json.dumps({
        OR_OPERATOR: [{field_name: val} for val in values]
    })
