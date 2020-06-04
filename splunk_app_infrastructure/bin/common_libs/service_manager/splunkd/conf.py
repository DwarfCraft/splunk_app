import http.client
import json
import sys
from os import path
from future.moves.urllib.parse import quote, quote_plus, urlencode
from future.moves.urllib.error import HTTPError
from future.moves.urllib.request import urlopen, Request

lib_dir = path.dirname(path.dirname(path.dirname(path.abspath(__file__))))  # noqa
sys.path.append(lib_dir)  # noqa
from . import BaseSplunkdServiceManager, SplunkdServiceManagerException
from logging_utils import log
from utils import to_bytes

logger = log.getLogger()


class ConfManagerInternalException(SplunkdServiceManagerException):
    def __init__(self, msg):
        super(ConfManagerInternalException, self).__init__(msg)


class ConfManagerStanzaNotFoundException(SplunkdServiceManagerException):
    def __init__(self, msg):
        super(ConfManagerStanzaNotFoundException, self).__init__(msg)


class ConfManager(BaseSplunkdServiceManager):
    """
    CONF file access, each conf manager instance manages stanzas in one conf file.
    To manage multiple conf files, create multiple conf managers.
    """

    def __init__(self, conf_file, server_uri,
                 session_key, app, user='nobody'):
        """
        Return CONF manager object
        """
        super(ConfManager, self).__init__(session_key, server_uri, app, user)
        self.conf_file = conf_file

    def _build_uri(self, stanza_name=None, query=None):
        """
        Create URI for CONF file CRUD operations

        :param stanza_name: stanza to perform operations on
        :param query: query params that will be written as key-value pairs to the conf file
        """
        base_uri = self.base_uri()
        query_params = dict(output_mode='json')
        if query:
            query_params.update(query)
        base_url = "%s/configs/conf-%s" % (base_uri, quote(self.conf_file))
        query_string = '?%s' % (urlencode(query_params))
        return '%s/%s' % (base_url, query_string) if not stanza_name else \
            '%s/%s%s' % (base_url, quote_plus(stanza_name), query_string)

    def _build_send_req(self, method, stanza_name=None, data=None, query=None):
        """
        Build request object

        :param method: HTTP Method
        :param data: body data
        :param stanza_name: stanza in conf file to write to
        :param query: query params
        :return: response object
        """
        headers = {
            'Authorization': 'Splunk %s' % self.session_key,
            'Content-Type': 'application/json'
        }
        '''
        The REALLY annoying thing about CONF endpoints is that, unlike KV store endpoints,
        the format in which they take data arguments is the application/x-www-form-urlencoded.
        This means, if you have {a: 'b', c: 'd'}, you would just stringify this for KV store calls
        but for CONF endpoints, you need to send it like &a=b&c=d.

        :param params: dict of data we want to convert to this other format
        :return: a formatted string like a=b&c=d&enough=nonsense
        '''
        try:
            data_string = to_bytes(urlencode(data)) if data else None
            req = Request(url=self._build_uri(stanza_name, query=query), data=data_string, headers=headers)
            req.get_method = lambda: method
            res = urlopen(req)
            return json.loads(res.read())
        except HTTPError as e:
            if e.code == http.client.NOT_FOUND:
                return None
            else:
                raise ConfManagerInternalException(e)

    def get_stanza(self, stanza_name):
        """
        get stanza with the specific stanza name

        :param stanza_name: name of the stanza
        """
        try:
            return self._build_send_req('GET', stanza_name)
        except Exception:
            raise ConfManagerInternalException(
                'Could not load stanza with name %s' % stanza_name)

    def load_stanzas(self, count=0, offset=0):
        """
        Load all stanzas in this conf file

        :param count: limitation
        :param offset: offset to load from
        :return: dict EAI response from CONF endpoint
        """
        try:
            return self._build_send_req('GET', query=dict(count=count, offset=offset))
        except Exception:
            raise ConfManagerInternalException("Could not load stanzas")

    def update_existing_stanza(self, stanza_name, data):
        """
        Update fields in stanza_name with key-value pairings in <data>

        :param stanza_name: stanza in conf file to update key-value pairs
        :param data: key-value pairs to update with
        :return: dict EAI response from CONF endpoint
        """
        try:
            return self._build_send_req('POST', stanza_name, data=data)
        except Exception:
            raise ConfManagerInternalException('Failed to update stanza named "%s"!' % stanza_name)

    def write_new_stanza(self, stanza_name, data):
        """
        Create new stanza in conf file with name <stanza_name> and key-value
        pairings given in <data>

        :param stanza_name: new stanza to create in CONF file
        :param data: key-value pairings to associate with new stanza
        :return: dict EAI response from CONF endpoint
        """
        try:
            return self._build_send_req(
                'POST',
                data=dict(name=quote_plus(stanza_name),
                          **data)
                )
        except Exception:
            raise ConfManagerInternalException('Failed to create stanza named "%s"' % stanza_name)

    def delete_stanza(self, stanza_name):
        """
        Delete stanza in CONF file

        :param stanza_name: stanza name in CONF file to delete
        :return: dict EAI response from CONF endpoint
        """
        try:
            return self._build_send_req('DELETE', stanza_name=stanza_name)
        except Exception as e:
            logger.error('Cannot delete username %s because: %s' % (stanza_name, e.message))
            raise ConfManagerStanzaNotFoundException('Cannot delete username %s' % stanza_name)
