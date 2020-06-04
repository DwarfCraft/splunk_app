import em_path_inject  # noqa

import re
from builtins import object
from functools import reduce
import http.client

import em_constants as EMConstants
from em_model_entity_class import EntityClass
from em_model_threshold import EMThreshold
import em_common
from service_manager.splunkd.search import SearchManager
from rest_handler.session import session

from utils.i18n_py23 import _
from rest_handler.exception import BaseRestException


class AlertInternalException(BaseRestException):

    def __init__(self, message):
        super(AlertInternalException, self).__init__(http.client.INTERNAL_SERVER_ERROR, message)


class AlertArgValidationException(BaseRestException):

    def __init__(self, message):
        super(AlertArgValidationException, self).__init__(http.client.BAD_REQUEST, message)


MANAGED_BY_TEMPLATE = '{app_name}:{managed_by}'


def parse_error_decorator_creator(error_str='Unknown alert syntax found'):
    """
    Creates a decorator with a specific error string for alert parsing issues
    """
    def parse_error_decorator(func):
        def wrapped_func(*args):
            try:
                return func(*args)
            except Exception:
                raise Exception(error_str)
        return wrapped_func
    return parse_error_decorator


class EMAlert(object):
    """
    EMAlert class handles alert related logic
    """
    # Validation related constants
    ALLOWED_TYPES = ['group', 'entity']

    # SPL template for constructing final query
    SPL_TEMPLATE = (
        '{metric_spl}'
        '| sort - _time'  # sort by _time so that latest value comes first
        '| stats list({aggregation}) as {aggregation_rename}, list(_time) as time {split_by_clause}'
        '| eval past_value=mvindex({aggregation_rename}, 1), current_value=mvindex({aggregation_rename}, 0), current_time=mvindex(time, 0)'  # noqa
        '| fields - {aggregation_rename}, time'
        '| eval CRITICAL=5, WARNING=3, INFO=1'
        '| eval past_state={past_against_threshold_spl}'
        '| eval current_state={current_against_threshold_spl}'
        '| eval state_change=if(current_state > past_state, "degrade", if(current_state == past_state, "no", "improve"))'  # noqa
        '| eval metric_name="{metric_name}",'  # put additional information into search result
        'aggregation_method="{aggregation_rename}",'
        'managed_by_id="{managed_by_id}",'
        'managed_by_type="{managed_by_type}",'
        'split_by="{split_by}",'
        'threshold_info_min={info_min},'
        'threshold_info_max={info_max},'
        'threshold_warning_min={warning_min},'
        'threshold_warning_max={warning_max},'
        'threshold_critical_min={critical_min},'
        'threshold_critical_max={critical_max},'
        'metric_filters_incl="{metric_filters_incl}",'
        'metric_filters_excl="{metric_filters_excl}",'
        'ss_id="{ss_id}"'
        '{join_with_entities_clause}'
    )
    # Extract patterns are used extract information from metric_spl
    EXTRACT_PATTERNS = {
        'AGGREGATION': r'\|\s*mstats\s*(?P<aggregation>\S*)\(',
        'SPLIT_BY': r'.*BY\s(?P<split_by>\w+)',
        'EARLIEST': r'earliest=\d*\.{0,}\d*\S{0,}',
        'LATEST': r'latest=\d*\.{0,}\d*\S{0,}',
        'SPAN': r'span=\d*\.{0,}\d*\S{0,}',
        'METRIC_NAME': r'.*metric_name="(?P<metric_name>\S+)"\s?'
    }

    # Regexes for SPL parsing
    MANAGED_BY_TYPE_REGEX = re.compile('managed_by_type="(.*?)"')
    METRIC_FILTERS_INCL_REGEX = re.compile('metric_filters_incl="([^"]*)"')
    METRIC_FILTERS_EXCL_REGEX = re.compile('metric_filters_excl="([^"]*)"')
    THRESHOLD_REGEX = re.compile(
        'threshold_info_min=([^,]*),threshold_info_max=([^,]*),threshold_warning_min=([^,]*),'
        'threshold_warning_max=([^,]*),threshold_critical_min=([^,]*),'
        'threshold_critical_max=([^,]*)'
    )

    def __init__(self, name, managed_by, managed_by_type, metric_spl, threshold,
                 actions=None, metric_filters=None):
        """
        initialize an EMAlert instance
        :param name: name of the alert
        :param managed_by: id of entity/group this alert belongs to
        :param managed_by_type: type of object that manages this alert
        :param metric_spl: SPL to get metric data -- type: string
               example: | mstats avg(_value) as "Avg" WHERE "host"="akron.usa.com" AND ("cpu"="0" OR "cpu"="1") AND metric_name="cpu.system" earliest=1521045946.014 latest=1521049546.014 span=10s BY "cpu"  # noqa
        :param threshold: threshold object -- type: EMThreshold
        :param actions: list of alert actions to take -- type: EMAlertAction (or its subclass)
        :param metric_filters: list of metric filters from MAW (list of dict)
        """
        self.name = name
        self.managed_by = managed_by
        self.managed_by_type = managed_by_type
        self.metric_spl = metric_spl.strip()
        self.threshold = threshold
        self.actions = [] if not actions else actions
        self.metric_filters = [] if not metric_filters else metric_filters
        self._validate()

    def _validate(self):
        self._validate_metric_spl()
        self._validate_managed_by_type()
        self._validate_metric_filters()

    def _validate_metric_spl(self):
        EMAlert._validate_spl_contains_no_data_modifying_commands(self.metric_spl)
        EMAlert._validate_spl_contains_no_unknown_macro(self.metric_spl, self.managed_by_type)
        EMAlert._validate_spl_access_control(self.metric_spl)

    @staticmethod
    def _validate_spl_contains_no_data_modifying_commands(metric_spl):
        tokenized_spl = metric_spl.split()
        data_modifying_commands = set([
            'outputcsv', 'outputlookup', 'outputtext',
            'collect', 'mcollect', 'meventcollect', 'tscollect'
        ])
        for token in tokenized_spl:
            if token in data_modifying_commands:
                raise AlertArgValidationException('metric SPL contains data modifying command - %s' % token)

    @staticmethod
    def _validate_spl_contains_no_unknown_macro(metric_spl, managed_by_type):
        regex = r'`[^`]+`'
        macros = re.findall(regex, metric_spl)
        for macro in macros:
            if 'group_filter' not in macro and 'sai_metrics_indexes' not in macro:
                raise AlertArgValidationException('metric SPL contains external macro - %s' % macro)

    @staticmethod
    def _validate_spl_access_control(metric_spl):
        """
        validate that metric SPL doesn't try to access data that should be
        unauthorized for the creating/modifying user
        """
        server_uri = em_common.get_server_uri()
        manager = SearchManager(server_uri, session['authtoken'], EMConstants.APP_NAME)
        response = manager.search(metric_spl)
        if 'results' not in response and 'messages' in response:
            for msg in response['messages']:
                if msg['type'] in ('ERROR', 'FATAL'):
                    raise AlertArgValidationException('Invalid metric SPL - Error: %s' % msg.get('text', ''))

    def _validate_managed_by_type(self):
        if self.managed_by_type not in EMAlert.ALLOWED_TYPES:
            raise AlertArgValidationException(_('Type: %(managed_by_type)s is not allowed.'))

    def _validate_metric_filters(self):
        for metric_filter in self.metric_filters:
            sorted_keys = sorted(metric_filter.keys())

            # validate regular metric filters - if 'search' is present in regular metric filter
            # it can be safely ignored
            if all(elem in sorted_keys for elem in ['field', 'type', 'values']):
                if metric_filter['type'] not in ['exclude', 'include']:
                    raise AlertArgValidationException(_('Unknown metric_filter type'))

            # validate macro metric filters
            elif all(elem in sorted_keys for elem in ['name', 'parameters', 'type']):
                if metric_filter['type'] != 'macro':
                    raise AlertArgValidationException(_('Unknown metric_filter type'))
            else:
                raise AlertArgValidationException(_('Unexpected metric_filter keys'))

    def _get_aggregation(self):
        """
        get aggregation method from SPL
        """
        aggreg_match = re.search(EMAlert.EXTRACT_PATTERNS['AGGREGATION'], self.metric_spl)
        if not aggreg_match:
            raise AlertInternalException(_('Aggregation method is missing from metric SPL'))
        return aggreg_match.group('aggregation')

    def _get_split_by(self):
        """
        get split by clause from SPL
        """
        split_by_match = re.match(EMAlert.EXTRACT_PATTERNS['SPLIT_BY'], self.metric_spl)
        if split_by_match:
            return split_by_match.group('split_by')
        return None

    def _get_metric_name(self):
        """
        get metric name from SPL
        """
        metric_name_match = re.match(EMAlert.EXTRACT_PATTERNS['METRIC_NAME'], self.metric_spl)
        if not metric_name_match:
            raise AlertInternalException(_('Metric name is missing from metric SPL'))
        metric_name = metric_name_match.group('metric_name')
        return metric_name

    def _build_join_entities_clause(self, managed_by_type, split_by=None):
        """
        get join with entities clause to fill in entities information
        :param managed_by_type: entity or group
        :param id_dim_field: only for group case
        :return:
        """
        # TODO: changes made here have migration impact that needs to be included as part of the migration work
        entity_spl_template = (
            '| eval entity_id=managed_by_id '
            '| lookup em_entity_cache _key as entity_id OUTPUT title as entity_title, _key as entity_id '
            '| fields - dimensions_kv, expiry_time'
        )
        group_spl_template = (
            # NOTE: wrap id_dim_field in single quotes so eval could work
            # with dimension name with non-alphanumeric characters
            '| eval lookup_field="{id_dim_field}="+\'{id_dim_field}\' '
            '| lookup em_entity_cache _dimensions_kv_lookup as lookup_field OUTPUT title as entity_title, _key as entity_id '  # noqa
            '| fields - dimensions_kv, expiry_time, lookup_field'
        )
        entity_class_list = EntityClass.load()
        identifier_dimensions = reduce(lambda ids1, ids2: ids1 + ids2,
                                       [ec.identifier_dimensions for ec in entity_class_list])
        join_clause = ''

        # group case
        if managed_by_type == EMAlert.ALLOWED_TYPES[0]:
            # if split by is an identifier dimension, use the group_spl_template. Else, do NOT create a join clause.
            if split_by and split_by in identifier_dimensions:
                join_clause = group_spl_template.format(
                    entities_store=EMConstants.STORE_ENTITY_CACHE, id_dim_field=split_by)
        # entity case
        else:
            join_clause = entity_spl_template.format(entities_store=EMConstants.STORE_ENTITY_CACHE)

        return join_clause

    def convert_spl(self):
        """
        convert alert to SPL
        :return: string - result SPL
        """
        # get aggregation method
        aggregation = self._get_aggregation()
        # get split by criteria
        split_by = self._get_split_by()
        split_by_clause = 'by "%s"' % split_by if split_by else ''
        # get metric name
        metric_name = self._get_metric_name()
        # modify time range and span
        # TODO: do we need to dynamically set earliest & latet based on collection window ??
        pattern_repl_list = [
            (EMAlert.EXTRACT_PATTERNS['EARLIEST'], ''),
            (EMAlert.EXTRACT_PATTERNS['LATEST'], ''),
            (EMAlert.EXTRACT_PATTERNS['SPAN'], 'span=1m')
        ]
        metric_spl = self.metric_spl
        for pattern, repl in pattern_repl_list:
            metric_spl = re.sub(pattern, repl, metric_spl)

        # build threshold SPL
        past_against_threshold_spl = self._build_threshold_spl('past_value')
        current_against_threshold_spl = self._build_threshold_spl('current_value')

        # Add filter data to the search SPL to pass it through to notifications
        filters_helper = {'include': [], 'exclude': []}
        for metric_filter in self.metric_filters:
            # skip the macro filters
            if metric_filter['type'] == 'macro':
                continue
            filters_helper[metric_filter['type']].append(
                '%s: %s' % (metric_filter['field']['name'],
                            ', '.join(metric_filter['values']))
            )
        metric_filters_incl = '; '.join(filters_helper['include'])
        metric_filters_excl = '; '.join(filters_helper['exclude'])
        spl = EMAlert.SPL_TEMPLATE.format(
            metric_spl=metric_spl,
            aggregation='"%s(_value)"' % aggregation,
            aggregation_rename=aggregation.capitalize(),
            split_by_clause=split_by_clause,
            past_against_threshold_spl=past_against_threshold_spl,
            current_against_threshold_spl=current_against_threshold_spl,
            metric_name=metric_name,
            managed_by_id=self.managed_by,
            managed_by_type=self.managed_by_type,
            split_by=split_by,
            metric_filters_incl=metric_filters_incl,
            metric_filters_excl=metric_filters_excl,
            ss_id=self.name,
            join_with_entities_clause=self._build_join_entities_clause(self.managed_by_type, split_by),
            **vars(self.threshold)
        )
        return spl

    def _build_threshold_spl(self, val_name):
        threshold_spl_template = (
            'if({val_name} >= {info_min} AND {val_name} < {info_max}, INFO, '
            'if({val_name} >= {warning_min} AND {val_name} < {warning_max}, WARNING, '
            'if({val_name} >= {critical_min} AND {val_name} < {critical_max}, CRITICAL, "None"'
            ')))'
        )
        return threshold_spl_template.format(
            val_name=val_name,
            **vars(self.threshold)
        )

    def to_params(self):
        """
        convert to splunk savedsearch params
        :return: dict
        """
        # add basic savedsearch data
        data = {
            'name': self.name,
            'alert.track': 1,
            'alert.severity': 6,
            'alert.managedBy': MANAGED_BY_TEMPLATE.format(
                app_name=EMConstants.APP_NAME,
                managed_by=self.managed_by
            ),
            'search': self.convert_spl(),
            # alert trigger condition settings
            'alert_condition': 'search state_change != "no"',
            'alert_type': 'custom',
            # set to run every 1 minute --  this could be something user configurable as well
            'cron_schedule': '*/1 * * * *',
            'is_scheduled': 1,
            # enable actions (REST doc is inaccurate -
            # https://docs.splunk.com/Documentation/Splunk/7.0.2/RESTREF/RESTsearch#saved.2Fsearches, actions cannot
            # be enabled by setting action.<action_name> to be 1)
            'actions': ','.join([ac.action_name for ac in self.actions]),
            # set earliest & latest time
            'dispatch.earliest_time': '-6m',
            'dispatch.latest_time': 'now'
        }
        # add custom alert action data
        for action in self.actions:
            data.update(action.to_params())
        return data

    #########################
    # Alert parsing methods #
    #########################
    # These should work with metric SPLs from any version of SAI for migration support

    @classmethod
    @parse_error_decorator_creator('Unknown alert syntax found for parsing managed by type')
    def parse_managed_by_type(cls, spl_string):
        """
        :param spl_string: SPL string representing an alert
        :return: string matching one of EMAlert.ALLOWED_TYPES
        """
        managed_by_types = cls.MANAGED_BY_TYPE_REGEX.findall(spl_string)
        if len(managed_by_types) != 1 or managed_by_types[0] not in EMAlert.ALLOWED_TYPES:
            raise Exception()
        return managed_by_types[0]

    @classmethod
    @parse_error_decorator_creator('Unknown alert syntax found for parsing metric filters')
    def parse_metric_filters(cls, spl_string):
        """
        :param spl_string: SPL string representing an alert
        :return: list of dicts representing the metric filters
        """
        def add_metric_filters_incl_excl_clause_to_list(target_list, clause, filter_type):
            if clause:
                filter_type_list = clause.split('; ')
                for each in filter_type_list:
                    key, values = each.split(': ')
                    target_list.append({
                        'type': filter_type,
                        'field': {
                            'name': key,
                        },
                        'values': values.split(', '),
                    })
        metric_filters = []
        metric_filters_incl_clauses = cls.METRIC_FILTERS_INCL_REGEX.search(spl_string).groups()
        metric_filters_excl_clauses = cls.METRIC_FILTERS_EXCL_REGEX.search(spl_string).groups()
        if len(metric_filters_incl_clauses) != 1 or len(metric_filters_excl_clauses) != 1:
            raise Exception()

        add_metric_filters_incl_excl_clause_to_list(metric_filters, metric_filters_incl_clauses[0],
                                                    'include')
        add_metric_filters_incl_excl_clause_to_list(metric_filters, metric_filters_excl_clauses[0],
                                                    'exclude')
        return metric_filters

    @classmethod
    @parse_error_decorator_creator('Unknown alert syntax found for parsing metric SPL')
    def parse_metric_spl(cls, spl_string):
        """
        :param spl_string: SPL string representing an alert
        :return: SPL string representing the first part of the alert
        """
        return '| %s' % spl_string.split('| ', 2)[1]

    @classmethod
    @parse_error_decorator_creator('Unknown alert syntax found for parsing threshold params')
    def parse_threshold_params(cls, spl_string):
        """
        :param spl_string: SPL string representing an alert
        :return: EMThreshold object
        """
        threshold_params = cls.THRESHOLD_REGEX.search(spl_string).groups()
        if len(threshold_params) != 6:
            raise Exception()
        threshold_params = [float(each) for each in threshold_params]
        return EMThreshold(*threshold_params)
