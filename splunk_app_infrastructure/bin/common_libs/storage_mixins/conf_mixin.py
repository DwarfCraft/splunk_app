from .base_mixin import AbstractBaseStorageMixin
from rest_handler.session import session, authtoken_required
from splunk import getDefault
from splunklib.client import Service


class ConfMixin(AbstractBaseStorageMixin):
    @classmethod
    def conf_stanzas(cls):
        svc = Service(
            port=getDefault('port'),
            token=session['authtoken'],
            app=cls.app_name(),
            owner='nobody',
        )
        conf = svc.confs[cls.storage_name()]
        return conf

    @classmethod
    @authtoken_required
    def storage_get(cls, stanza_name):
        conf = cls.conf_stanzas()
        try:
            stanza = conf[stanza_name]
            return stanza
        except KeyError:
            return None
        except Exception as e:
            raise e

    @classmethod
    @authtoken_required
    def storage_load(cls):
        stanzas = cls.conf_stanzas()
        return stanzas

    @classmethod
    @authtoken_required
    def storage_save(cls, key, data):
        conf = cls.conf_stanzas()
        stanza = conf[key]
        stanza.update(**data)
