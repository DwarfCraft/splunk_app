"""
(C) 2019 Splunk Inc. All rights reserved.


Module to help format error messages returned from Splunk

Splunk error text is returned as json blob in the following format:

{
    "messages": [
        {
            "type": "FATAL",
            "text": "The error message"
        }
    ]
}
"""

import json


def format_error(error_type, text):
    error_type_string = ''
    if error_type:
        error_type_string = '[%s] ' % error_type
    return "%s%s" % (error_type_string, text)


def format_splunk_error(code, messages):
    """
    Format an error message based on a splunk error code and a messages array returned from request errors
    :param code:
    :param messages:
    :return:
    """
    message = ''
    if messages:
        d = json.loads(messages)
        if 'messages' in d:
            text_list = [format_error(error_object['type'], error_object['text']) for error_object in d['messages']]
            message = ', '.join(text_list)
    return '%s: %s' % (code, message)
