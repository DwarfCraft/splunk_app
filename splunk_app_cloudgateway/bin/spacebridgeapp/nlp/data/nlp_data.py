"""
(C) 2019 Splunk Inc. All rights reserved.

Module for representation of data objects for alerts
"""

from spacebridgeapp.data.base import SpacebridgeAppBase

class AuthToken(SpacebridgeAppBase):
    """AuthToken class which encapuslates all Auth Information for IMS client.
    """

    def __init__(self, deployment_id=None, mapped_user_id=None, can_manage_intents=False, timestamp=None):

        self.deployment_id = deployment_id
        self.can_manage_intents = can_manage_intents
        self.mapped_user_id = mapped_user_id
        self.timestamp = timestamp
