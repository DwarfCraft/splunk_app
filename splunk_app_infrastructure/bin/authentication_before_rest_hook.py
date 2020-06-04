import em_path_inject  # noqa

import json
import splunk.rest as rest
import em_common
from rest_handler.hooks import BeforeHandleHook
from rest_handler.session import session


class AuthenticationRestHook(BeforeHandleHook):
    """
    AuthenticationRestHook reads the current roles of the user and saves them to session
    """

    def before_handle(self, request):
        endpoint = '%s/services/authentication/current-context' % em_common.get_server_uri()
        _resp, content = rest.simpleRequest(
            endpoint,
            method='GET',
            getargs={'output_mode': 'json'},
            sessionKey=session['authtoken']
        )
        content = json.loads(content)
        roles = content['entry'][0]['content']['roles']
        session.save(roles=roles)
