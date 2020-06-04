"""
(C) 2019 Splunk Inc. All rights reserved.
"""


class SodiumProcessError(Exception):
    def __init__(self):
        self.message = "libsodium server process has stopped"

    def __repr__(self):
        return self.message


class SodiumOperationError(Exception):
    def __init__(self):
        self.message = "libsodium operation failed"

    def __repr__(self):
        return self.message
