"""
(C) 2019 Splunk Inc. All rights reserved.

Method used to help generate random guids
"""

import uuid


def get_guid():
    """
    Helper method to generate a unique guid
    :return:
    """
    return str(uuid.uuid4())
