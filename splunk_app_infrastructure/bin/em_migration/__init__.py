from __future__ import absolute_import
from collections import OrderedDict, namedtuple

from .base_migration_handler import BaseMigrationHandler  # noqa
from . import migration_handlers_2_0_0, migration_handlers_2_1_0

MigrationHandler = namedtuple('MigrationHandler', ['version', 'content'])

migration_handlers_dict = OrderedDict([
    MigrationHandler(
        version='1.4.0',
        content={}
    ),
    MigrationHandler(
        version='2.0.0',
        content={
            'minimal_version': '1.0.0',
            'handlers': [
                migration_handlers_2_0_0.AlertsMigrationHandler,
            ]
        }
    ),
    MigrationHandler(
        version='2.1.0',
        content={
            'minimal_version': '1.0.0',
            'handlers': [
               migration_handlers_2_1_0.StaticEntityToDynamicEntity,
            ]
        }
    )
])
