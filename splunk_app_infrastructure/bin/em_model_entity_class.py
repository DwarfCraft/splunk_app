import em_path_inject  # noqa
import json
import uuid

from logging_utils import log
from rest_handler.session import authtoken_required
from em_base_persistent_object import EMBasePersistentObject
from storage_mixins import ConfMixin

import em_constants

try:
    basestring
except NameError:
    basestring = str


class EntityClassInternalException(Exception):
    pass


class InvalidEntityClassException(Exception):
    pass


logger = log.getLogger()


ENTITY_CLASS_CONF = 'entity_classes'
ENTITY_CLASS_ALERT_ACTION = 'em_write_entity_summary'


class EntityClass(EMBasePersistentObject, ConfMixin):
    """
    The `EntityClass` model that handles the interpretation and transformation of an entity class.
    Provides methods that talk to other services (e.g. Savedsearch).

    NOTE: each entity class can discover and save information of 200,000 entities maximum, this limit
    can be adjusted by changing the value of max_action_results in limits.conf
    """

    VALID_CLASS_TYPES = ['metric', 'event', 'csv']
    SAVEDSEARCH_PREFIX = 'Entity Class - '

    def __init__(
        self,
        key,
        title,
        class_type,
        source_filter,
        identifier_dimensions,
        informational_dimensions,
        blacklisted_dimensions,
        title_dimension,
        monitoring_window,
        cron_schedule,
        status_transform=None,
        retirement_policy=None,
        correlation_rules=None,
        vital_metrics=None,
        dimension_display_names=None,
    ):
        self.key = key
        self.title = title
        self.class_type = class_type
        self.source_filter = source_filter
        self.identifier_dimensions = identifier_dimensions
        if isinstance(self.identifier_dimensions, list):  # To keep consistent error-throwing
            self.identifier_dimensions.sort()
        self.informational_dimensions = informational_dimensions
        self.blacklisted_dimensions = blacklisted_dimensions
        self.title_dimension = title_dimension
        self.monitoring_window = monitoring_window
        self.cron_schedule = cron_schedule
        self.status_transform = status_transform
        self.retirement_policy = retirement_policy if retirement_policy else []
        self.correlation_rules = correlation_rules if correlation_rules else {}
        self.vital_metrics = vital_metrics if vital_metrics else []
        self.dimension_display_names = dimension_display_names if dimension_display_names else []
        self._service = None
        self._validate()

    def _validate(self):
        errs = []
        if self.class_type not in EntityClass.VALID_CLASS_TYPES:
            errs.append(
                'entity_class should be one of %s instead of %s' % (EntityClass.VALID_CLASS_TYPES, self.class_type)
            )
        if not isinstance(self.source_filter, basestring):
            errs.append('source_filter should be "basestring" instead of "%s"' % type(self.source_filter))
        if not isinstance(self.identifier_dimensions, list):
            errs.append('identifier_dimensions should be "list" instead of "%s"' % type(self.identifier_dimensions))
        if not (isinstance(self.informational_dimensions, list) or self.informational_dimensions == '*'):
            errs.append(
                'informational_dimensions should be "list" or "*" instead of %s' % type(self.informational_dimensions)
            )
        if not isinstance(self.blacklisted_dimensions, list):
            errs.append('blacklisted_dimensions should be "list" instead of "%s"' % type(self.blacklisted_dimensions))
        if len(set(self.blacklisted_dimensions).intersection(set(self.identifier_dimensions))):
            errs.append('blacklisted_dimensions cannot include identifier_dimensions')
        if len(set(self.informational_dimensions).intersection(set(self.identifier_dimensions))):
            errs.append('informational_dimensions cannot include identifier_dimensions')
        if not isinstance(self.title_dimension, basestring):
            errs.append('title_dimensions should be "basestring" instead of "%s"' % type(self.title_dimension))
        if not isinstance(self.monitoring_window, int):
            errs.append('monitoring_window should be "int" instead of "%s"' % type(self.monitoring_window))
        if not isinstance(self.cron_schedule, basestring):
            errs.append('cron_schedule should be "basestring" instead of "%s"' % type(self.cron_schedule))
        if not isinstance(self.correlation_rules, dict):
            errs.append('correlation_rules should be "dict" instead of "%s"' % type(self.correlation_rules))
        if not isinstance(self.vital_metrics, list):
            errs.append('vital_metrics should be "list" instead of "%s"' % type(self.vital_metrics))
        if not isinstance(self.dimension_display_names, list):
            errs.append('dimension_display_names should be "list" instead of "%s"' % type(self.dimension_display_names))
        if not isinstance(self.retirement_policy, list):
            errs.append('retirement_policy should be "list" instead of "%s"' % type(self.retirement_policy))
        if len(errs):
            err_msg = 'entity class: %s - Error: %s' % (self.key, '. '.join(errs))
            raise InvalidEntityClassException(err_msg)

    @classmethod
    def storage_name(cls):
        return ENTITY_CLASS_CONF

    @classmethod
    def _from_raw(cls, stanza):
        correlation_rules_val = stanza['correlation_rules']
        correlation_rules = json.loads(correlation_rules_val) if correlation_rules_val else {}

        vital_metrics_val = stanza['vital_metrics']
        vital_metrics = json.loads(vital_metrics_val) if vital_metrics_val else []

        dim_display_names_val = stanza['dimension_display_names']
        dim_display_names = json.loads(dim_display_names_val) if dim_display_names_val else []

        retirement_policy_val = stanza['retirement_policy']
        retirement_policy = json.loads(retirement_policy_val) if retirement_policy_val else []

        return EntityClass(
            key=stanza['name'],
            title=stanza['title'],
            class_type=stanza['type'],
            source_filter=stanza['source_filter'],
            identifier_dimensions=json.loads(stanza['identifier_dimensions']),
            informational_dimensions=json.loads(stanza['informational_dimensions']),
            blacklisted_dimensions=json.loads(stanza['blacklisted_dimensions']),
            title_dimension=stanza['title_dimension'],
            monitoring_window=int(stanza['monitoring_window']),
            cron_schedule=stanza['cron_schedule'],
            status_transform=stanza['status_transform'],
            retirement_policy=retirement_policy,
            correlation_rules=correlation_rules,
            vital_metrics=vital_metrics,
            dimension_display_names=dim_display_names
        )

    def _raw(self):
        raise NotImplementedError()

    @authtoken_required
    def upsert_savedsearch(self):
        """
        Convert this entity class to a savedsearch and upsert it as a stanza into savedsearch.conf
        """
        options = self.get_savedsearch_options()
        search = self.get_full_search_spl()
        savedsearch_name = EntityClass.SAVEDSEARCH_PREFIX + self.key
        logger.debug('savedsearch: %s,  SPL: %s' % (savedsearch_name, search))
        try:
            existing_savedsearch = self.service.saved_searches[savedsearch_name]
            existing_savedsearch.update(
                search=search,
                **options
            )
        except KeyError:
            self.service.saved_searches.create(
                name=savedsearch_name,
                search=search,
                **options
            )
        except Exception as e:
            logger.error('Failed to upsert savedsearch for entity class %s - Error: %s' % (self.key, e))
            raise EntityClassInternalException(e)

    def get_savedsearch_options(self):
        """
        Get savedsarch options from atttributes of this entity class along with default options
        for all entity class defined savedsearches
        """
        return {
            'actions': ENTITY_CLASS_ALERT_ACTION,
            'action.{}'.format(ENTITY_CLASS_ALERT_ACTION): 1,
            'cron_schedule': self.cron_schedule,
            'is_scheduled': 1,
            'schedule_priority': 'highest',
            'alert_condition': 'search key=*',
            'alert.managedBy': '{app}:entity_class:{entity_class_key}'.format(
                app=em_constants.APP_NAME,
                entity_class_key=self.key
            )
        }

    def get_full_search_spl(self):
        """
        Get Splunk search SPL based on the attributes of this entity class. The SPL is composed of different
        components.
        For details read: https://confluence.splunk.com/display/ITOA/%5BERD%5D+Dynamic+Entity+Model+for+SAI
        """
        dimensions_kv_transform_clause = (
            '| foreach dimension.*'
            # setting a placeholder value since mvexpanding on null value yields no results
            '[| eval "<<FIELD>>"=coalesce(\'<<FIELD>>\', "null_value_placeholder")'
            '| mvexpand "<<FIELD>>"'
            # resetting the placeholder back to null()
            '| eval "<<FIELD>>"=if(\'<<FIELD>>\'="null_value_placeholder", null(), \'<<FIELD>>\')'
            # check if field is an identifier dimension
            '| eval is_identifier=if(match("<<MATCHSTR>>", "identifier"), 1, 0)'
            '| eval "<<MATCHSTR>>"=substr("<<MATCHSTR>>", len(if(is_identifier=1, "identifier.", "info.")) + 1) + "=" + \'<<FIELD>>\', dimensions_kv=mvappend(dimensions_kv, \'<<MATCHSTR>>\')] '  # noqa
            '| fields key, title, dimensions_kv, entity_class, mod_time, expiry_time, identifier_dimensions'
            '| stats values(*) as * by key'
        )
        full_spl = ''
        if self.class_type == 'metric':
            dataset_search = self._get_metric_dataset_search()
            entity_class_info_enrichment_clause = self._get_entity_class_info_enrichment_spl()
            full_spl = dataset_search + \
                entity_class_info_enrichment_clause + \
                dimensions_kv_transform_clause
        return full_spl

    def _get_metric_dataset_search(self):
        """
        Get the dataset search clause for metrics entity class.
        The results of the dataset are used to define entities.
        """
        template = (
            '| mcatalog {id_dims_values} {info_dims_values} where {source_filter} earliest=-{monitoring_window}s by {id_dims_list}'  # noqa
            '| fields dimension.*'
        )
        id_dims_values = ' '.join(
            ['values("{dim}") as "dimension.identifier.{dim}"'.format(dim=d) for d in self.identifier_dimensions]
        )
        if isinstance(self.informational_dimensions, list) and len(self.informational_dimensions):
            info_dims_values = ' '.join(
                ['values("{dim}") as "dimension.info.{dim}"'.format(dim=d) for d in self.informational_dimensions]
            )
        elif self.informational_dimensions == '*':
            quoted_info_dim_exclusion_list = [
                '"{}"'.format(dim) for dim in (self.blacklisted_dimensions + self.identifier_dimensions)
            ]
            info_dim_exclusion_clause = ' AND '.join([
                'info != %s' % dim for dim in quoted_info_dim_exclusion_list
            ])
            info_dims_subsearch = (
                '[ mcatalog values(_dims) as info where {source_filter} earliest=-{monitoring_window}s'
                # NOTE: the following append is to avoid situations when there's no data the subsearch would make the
                # main discovery search invalid as mentioned in SII-6101. The search overhead added should be minimal.
                '| append [ | makeresults | eval info="no-data-placeholder"| fields - _time]'
                '| mvexpand info'
                '| search {info_dim_exclusion_clause}'
                '| eval search="values(" . "\\\"" . info . "\\\"" . ") as " . "\\\"" . "dimension.info." . info . "\\\""'  # noqa
                '| fields search'
                '| mvcombine search'
                '| nomv search'
                ']'
            ).format(
                source_filter=self.source_filter,
                info_dim_exclusion_clause=info_dim_exclusion_clause,
                monitoring_window=self.monitoring_window
            )
            info_dims_values = info_dims_subsearch
        else:
            raise InvalidEntityClassException('Invalid informational_dimension for entity class')
        dataset_search = template.format(
            id_dims_values=id_dims_values,
            info_dims_values=info_dims_values,
            source_filter=self.source_filter,
            monitoring_window=self.monitoring_window,
            id_dims_list=','.join(['"{}"'.format(dim) for dim in self.identifier_dimensions])
        )
        return dataset_search

    def _get_event_dataset_search(self):
        raise NotImplementedError()

    def _get_csv_dataset_search(self):
        raise NotImplementedError()

    def _get_entity_class_info_enrichment_spl(self):
        """
        Get SPL clause that's used to enrich each entity record with information
        about the entity class that discovers it.
        """
        delimiter = '${}$'.format(uuid.uuid4().hex)
        id_dims_concat = delimiter.join(self.identifier_dimensions)
        id_dims_concat_expr = ' + ":" + '.join(
            ['\'dimension.identifier.{}\''.format(dim) for dim in self.identifier_dimensions]
        )
        title_dim = 'dimension.{type}.{dim}'.format(
            type='identifier' if self.title_dimension in self.identifier_dimensions else 'info',
            dim=self.title_dimension
        )
        enrichment_spl = (
            '| eval entity_class="{entity_class}", mod_time=now(), expiry_time=mod_time+{monitoring_window}'
            '| eval identifier_dimensions=\"{id_dims_concat}\"'
            '| makemv delim=\"{delim}\" identifier_dimensions'
            '| eval key=sha256({id_dims_concat_expr} + ":" + entity_class), title=\'{title_dim}\''
        ).format(
            entity_class=self.key,
            monitoring_window=self.monitoring_window,
            id_dims_concat=id_dims_concat,
            delim=delimiter,
            id_dims_concat_expr=id_dims_concat_expr,
            title_dim=title_dim
        )
        return enrichment_spl
