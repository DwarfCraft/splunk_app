#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Splunk specific dependencies
import sys

from spacebridgeapp.util import py23

import psutil
from splunklib.searchcommands import dispatch, GeneratingCommand, Configuration, Option, validators

CLOUDGATEWAY_PROCESS_NAME = 'cloudgateway_modular_input.py'
SUBSCRIPTION_PROCESS_NAME = 'subscription_modular_input.py'
SODIUM_PROCESS_MATCH = 'libsodium-server'

CLOUDGATEWAY_KEY = 'cloudgateway'
SUBSCRIPTION_KEY = 'subscription'
CLOUDGATEWAY_SODIUM_KEY = 'cloudgateway_sodium'
SUBSCRIPTION_SODIUM_KEY = 'subscription_sodium'


def _check_for_script(cmdline, script_name):
    for arg in cmdline:
        if arg.endswith(script_name):
            return True
    return False


def _check_for_sodium_child(children):
    for child in children:
        if child.name().startswith(SODIUM_PROCESS_MATCH):
            return True
    return False


@Configuration(type='reporting')
class CloudgatewayPidCheck(GeneratingCommand):
    """
    This command checks that there are two python processes (websocket, subscriptions) running and that there are
    sodium processes attached to each.
    """

    def generate(self):
        status = {
            CLOUDGATEWAY_KEY: False,
            SUBSCRIPTION_KEY: False,
            CLOUDGATEWAY_SODIUM_KEY: False,
            SUBSCRIPTION_SODIUM_KEY: False
        }

        for p in psutil.process_iter():
            try:
                p.cmdline()
            except psutil.AccessDenied:
                continue

            if _check_for_script(p.cmdline(), CLOUDGATEWAY_PROCESS_NAME):
                status[CLOUDGATEWAY_KEY] = True
                status[CLOUDGATEWAY_SODIUM_KEY] = _check_for_sodium_child(p.children())
            elif _check_for_script(p.cmdline(), SUBSCRIPTION_PROCESS_NAME):
                status[SUBSCRIPTION_KEY] = True
                status[SUBSCRIPTION_SODIUM_KEY] = _check_for_sodium_child(p.children())
        yield status

dispatch(CloudgatewayPidCheck, sys.argv, sys.stdin, sys.stdout, __name__)
