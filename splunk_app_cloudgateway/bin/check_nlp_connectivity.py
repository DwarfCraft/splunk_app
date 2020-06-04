#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Splunk specific dependencies
import sys, os

from splunk.clilib.bundle_paths import make_splunkhome_path
from spacebridgeapp.util import py23


from requests.exceptions import ProxyError
from splunklib.searchcommands import dispatch, GeneratingCommand, Configuration, Option, validators
from spacebridgeapp.util.config import cloudgateway_config as config

# Command specific dependencies
import requests

@Configuration(type='reporting')
class CloudgatewayHttpsCheck(GeneratingCommand):
    """
    This command will allow a user to check if any webpage is reachable by allowing a user to enter a url string. 
    At this time, a 404 from either ims.prod-nlp.spl.mobi or auths.prod-nlp.spl.mobi is considered a success for connectivity. 
    Any http return other than 200 or 404 is considered a failure.  By default it will inherit Splunk's proxy settings and use
    them.  In the command you can disable the proxy by passing useProxy=False.
    """

    useProxy = Option(require=False, validate=validators.Boolean(), default=True)
    url = Option(require=True)

    def generate(self):

        url = self.url
        proxies = config.get_proxies()

        # Unset proxy, if unsetProxy = True
        if not self.useProxy:
            proxies = {}

        # Load data from REST API
        try:
            response = requests.get(
                url,
                proxies=proxies,
                timeout=15
            )

            response.raise_for_status()
            healthy = {'connected': True}
    
        except requests.exceptions.HTTPError as err:
            healthy = {'connected': False, 'message': err.message}
        except ProxyError as err:
            healthy = {'connected': False, 'message': err.message}

        yield healthy

    ''' HELPERS '''

dispatch(CloudgatewayHttpsCheck, sys.argv, sys.stdin, sys.stdout, __name__)
