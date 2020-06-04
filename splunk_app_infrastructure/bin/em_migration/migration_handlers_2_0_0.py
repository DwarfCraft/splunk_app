import em_path_inject # noqa

from splunk import getDefault
import re

import em_common
import em_constants
from service_manager.splunkd.savedsearch import SavedSearchManager
from solnlib.acl import ACLManager
from .base_migration_handler import BaseMigrationHandler


class AlertsMigrationHandler(BaseMigrationHandler):

    description = 'Migrate SAI Alerts with new permissions setting and SPLs'

    def __init__(self, logger, session_key):
        super(AlertsMigrationHandler, self).__init__(logger, session_key)

        self.saved_search_manager = SavedSearchManager(
            session_key=self.session_key,
            server_uri=em_common.get_server_uri(),
            app=em_constants.APP_NAME,
        )
        self.ACL_manager = ACLManager(
            self.session_key,
            app=em_constants.APP_NAME,
            port=getDefault('port'),
        )

    def _calculate_changes(self):
        # This function intentionally left blank
        return

    def _apply_changes(self):
        saved_searches = self.saved_search_manager.load(
            search="alert.managedBy=splunk_app_infrastructure:*"
        )["entry"]
        self.migrate_alerts_ownership(saved_searches)
        self.migrate_aws_metric_alerts_spl(saved_searches)

    def migrate_alerts_ownership(self, alert_savedsearches):
        '''
        Migrate the "owner" of all alert savedsearches to "nobody"
        '''
        for search in alert_savedsearches:
            self.ACL_manager.update("saved/searches/%s/acl" % search["name"],
                                    owner="nobody")
        self.logger.info('finished ownership migration for all alert savedsearches')

    def migrate_aws_metric_alerts_spl(self, alert_savedsearches):
        '''
        Migrate all alert savedsearches on AWS related metrics to new metric_name format
        specified in AWS TA 5.0
        '''
        metric_name_regexp = re.compile(r'metric_name="(?P<metric_name>AWS\/\w+\.\w+)"')
        for search in alert_savedsearches:
            content = search['content']
            spl = content.get('search')
            if spl is None:
                self.logger.warning('skipping alert %s - empty search SPL' % search['name'])
                continue
            metric_name_matches = metric_name_regexp.findall(spl)
            if not len(metric_name_matches):
                continue
            old_metric_name = metric_name_matches[0]
            new_metric_name = '{}.Average'.format(old_metric_name)
            new_spl = spl.replace(old_metric_name, new_metric_name)
            self.saved_search_manager.update(search['name'], {
                'search': new_spl
            })
        self.logger.info('finished alert SPL metric name migration for all AWS alert savedsearches')
