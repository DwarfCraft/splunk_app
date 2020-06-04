"""
(C) 2019 Splunk Inc. All rights reserved.

Helper function to convert different types to UTF-8 Strings
"""


def to_utf8_str(value):
    if isinstance(value, list):
        return list_to_str(value)
    elif value is None:
        return ''
    else:
        return str(value).encode('utf-8')


def list_to_str(list_of_values):
    return str([str(value).encode('utf-8') for value in list_of_values]).encode('utf-8')
