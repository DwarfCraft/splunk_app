import json

from spacebridgeapp.ar.data.data_class_mixin import DataClassMixin
from spacebridgeapp.util.constants import KEY
from spacebridgeapp.util.word_list import random_words

HOSTNAME_FIELD = 'hostname'
DEPLOYMENT_NAME_FIELD = 'deployment_name'


class PhantomMetadata(DataClassMixin):
    # There should only ever be one Phantom instance associated with this Splunk instance. This key value is used so we
    # never accidentally create multiple Phantom metadata entries in KV store.
    key = 'phantom-configuration'

    def __init__(self, hostname, deployment_name=None):
        self.hostname = hostname
        self.deployment_name = deployment_name

    @property
    def domain(self):
        return 'https://{}'.format(self.hostname)

    def to_dict(self, include_key=True):
        d = {HOSTNAME_FIELD: self.hostname}
        if self.deployment_name:
            d[DEPLOYMENT_NAME_FIELD] = self.deployment_name
        if include_key:
            d[KEY] = self.key
        return d

    def to_json(self):
        return json.dumps(self.to_dict())

    @staticmethod
    def from_json(phantom_metadata_json):
        if HOSTNAME_FIELD not in phantom_metadata_json:
            raise ValueError('"{}" must be a field in the Phantom metadata KV store entry.'.format(HOSTNAME_FIELD))
        return PhantomMetadata(hostname=phantom_metadata_json[HOSTNAME_FIELD],
                               deployment_name=phantom_metadata_json.get(DEPLOYMENT_NAME_FIELD))

    def __repr__(self):
        return 'PhantomMetadata(hostname={}, deployment_name={})'.format(self.hostname, self.deployment_name)


def generate_phantom_deployment_name():
    """Creates a random deployment name to identify Phantom within the Splapp and to AR iOS app users."""
    return ''.join(random_words(3))

