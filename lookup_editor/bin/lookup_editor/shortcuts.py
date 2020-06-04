"""
This module includes generic functions useful when processing lookup files.
"""

import re
import os
import csv
import json
from collections import OrderedDict, Sequence
import logging

from six import StringIO # For converting KV store array data to CSV for export
from six import string_types

from splunk.clilib.bundle_paths import make_splunkhome_path

def append_if_not_none(prefix, key, separator="."):
    """
    Append the given prefix if the prefix isn't empty.
    """

    if prefix is not None and len(prefix) > 0:
        return prefix + separator + key
    else:
        return key

def flatten_dict(dict_source, output=None, prefix='', fields=None):
    """
    Flatten a dictionary to an array
    """

    # Define the resulting output if it does not exist yet
    if output is None:
        output = OrderedDict()

    # Convert each entry in the dictionary
    for key in dict_source:
        value = dict_source[key]

        # Determine if this entry needs to turned into a text blob (such as converting a
        # dictionary or array into a string)
        if fields is not None and append_if_not_none(prefix, key) in fields:
            treat_as_text_blob = True
        else:
            treat_as_text_blob = False

        # If this isn't a listed column, then just include the raw JSON
        # This is necessary when a KV store has recognition for many of the fields but some
        # are expected to be JSON within a field, _not_ separate fields.
        if treat_as_text_blob and (isinstance(value, dict)
                                   or isinstance(value, OrderedDict)
                                   or (isinstance(value, Sequence)
                                       and not isinstance(value, string_types))):

            output[append_if_not_none(prefix, key)] = json.dumps(value)

        # Flatten out this dictionary or array entry
        elif isinstance(value, dict) or isinstance(value, OrderedDict):

            flatten_dict(value, output, append_if_not_none(prefix, key),
                         fields=fields)

        # If the value is a single item
        else:
            output[append_if_not_none(prefix, key)] = value

    return output

def escape_filename(file_name):
    """
    Return a file name the excludes special characters (replaced with underscores)
    """

    return re.sub(r'[/\\?%*:|"<>]', r'_', file_name)

def convert_array_to_csv(array):
    """
    Convert an array to CSV format.
    """

    output = StringIO()

    writer = csv.writer(output)

    for row in array:
        writer.writerow(row)

    return output.getvalue()

def make_lookup_filename(lookup_file, namespace="lookup_editor", owner=None):
    """
    Create the file name of a lookup file. That is, device a path for where the file should
    exist.
    """

    # Strip out invalid characters like ".." so that this cannot be used to conduct an
    # directory traversal
    lookup_file = os.path.basename(lookup_file)
    namespace = os.path.basename(namespace)

    if owner is not None:
        owner = os.path.basename(owner)

    # Get the user lookup
    if owner is not None and owner != 'nobody' and owner.strip() != '':
        return make_splunkhome_path(["etc", "users", owner, namespace, "lookups", lookup_file])

    # Get the non-user lookup
    else:
        return make_splunkhome_path(["etc", "apps", namespace, "lookups", lookup_file])

def is_lookup_in_users_path(lookup_file_path):
    """
    Determine if the lookup is within the user's path as opposed to being within the apps path.
    """

    if "etc/users/" in lookup_file_path:
        return True
    else:
        return False

def is_file_name_valid(lookup_file):
    """
    Indicate if the lookup file is valid (doesn't contain invalid characters such as "..").
    """

    allowed_path = re.compile("^[-A-Z0-9_ ]+([.][-A-Z0-9_ ]+)*$", re.IGNORECASE)

    if not allowed_path.match(lookup_file):
        return False
    else:
        return True
