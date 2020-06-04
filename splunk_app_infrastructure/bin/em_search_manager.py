# Copyright 2016 Splunk Inc. All rights reserved.
# Environment configuration
# N/A
# Standard Python Libraries
# Third-Party Libraries
from builtins import zip
import em_common
import em_constants as EMConstants
# Custom Libraries
# N/A
import em_path_inject  # noqa
from service_manager.splunkd.search import SearchManager
from logging_utils import log

logger = log.getLogger()


class EMSearchManager(SearchManager):
    """
    Search REST Endpoint service
    """

    def __init__(self, server_uri, session_key, app, owner='nobody'):
        super(EMSearchManager, self).__init__(server_uri, session_key, app, owner)

    CUSTOM_SEARCH_CMD = 'emgroupentitymatch'

    def get_all_dims_from_dims_name(self,
                                    predicate=[],
                                    id_dims_name=[],
                                    dims_name=[],
                                    earliest='-24h',
                                    latest='now',
                                    count=0):
        """
        Get list of dimensions name-value for all entities

        :param predicate: What metric to search for.
            i.e. cpu.* (All metric has metric_name starts by cpu.*)
        :param id_dims_name: Set of dimensions to identify entity
            i.e. ['ip','host']
        :pram dims_name: Set of dimensions name to search for
            i.e. ['ip', 'db_instance_id','host']
        :param earliest: earliest time
        :param latest: latest time
        :param count: limit number of result
        :return: list of dimensions for all entities
        """
        values_part = ''
        for d in dims_name:
            if d not in id_dims_name:
                values_part += 'values("%s") as "%s" ' % (d, d)
        id_dims_name = ['"%s"' % d for d in id_dims_name]
        metric_name_filter = ' OR '.join(['metric_name="' + x + '"' for x in predicate])
        id_predicate = ','.join(id_dims_name)
        if values_part:
            spl = '| mcatalog %s WHERE (%s) AND (`sai_metrics_indexes`) BY %s' % (
                values_part, metric_name_filter, id_predicate)
        else:
            spl = '| mcatalog values(host) WHERE (%s) AND (`sai_metrics_indexes`) BY %s | table host' % (
                metric_name_filter, id_predicate)
        results = self.search(spl, earliest, latest, count)
        res = []
        if 'results' in results and len(results['results']) > 0:
            res = results['results']
            logger.info('Received dimensions for all entities')
        return em_common.always_list(res)

    def get_dimension_names_by_id_dims(self,
                                       predicate=[],
                                       id_dims_name=[],
                                       earliest='-24h',
                                       latest='now',
                                       count=0):
        """
        Get dimension names by identifier_dimensions

        :param predicate: What metric to search for.
            i.e. cpu.* (All metric has metric_name starts by cpu.*)
        :param id_dims_name: List of dimensions name to identify entity
            i.e. ['ip', 'host']
        :param earliest: earliest time
        :param latest: latest time
        :param count: limit number of result
        :return: [{dims:['os','tag']}, {dims:['os','env']}]
        """
        iden_fields = set(id_dims_name)
        fields_part = ''
        for iden in iden_fields:
            fields_part += 'values("%s") ' % iden
        iden_fields = ['"%s"' % d for d in iden_fields]
        fields_list = ', '.join(iden_fields)
        metric_name_filter = ' OR '.join(['metric_name="' + x + '"' for x in predicate])
        spl = ('| mcatalog %s, values("_dims") as "dims" WHERE (%s) AND (`sai_metrics_indexes`) BY %s '
               '| table dims') % (fields_part, metric_name_filter, fields_list)
        results = self.search(spl, earliest, latest, count)
        res = []
        if 'results' in results and len(results['results']) > 0:
            res = results['results']
            logger.info('Retrieved dimension names by identifier dimensions')
        return em_common.always_list(res)

    def get_metric_names_by_dim_names(self,
                                      dimensions={},
                                      earliest='-24h',
                                      latest='now',
                                      count=0):
        """
        Get metric names by dimension names

        :param dimensions: Dictionary of dimension name and values.
            Dimension values should support *
            i.e. {'location': ['seattle', 'san francisco'], 'os': ['ubuntu', '*']}
        :param earliest: earliest time
        :param latest: latest time
        :param count: limit number of result
        :return: [{metric_names:['cpu.idle','cpu.nice']}]
        """
        # mstats requires metric_name keyword after WHERE
        mstats_base_command = '| mstats min(_value) as min, max(_value) as max WHERE metric_name=* AND \
                            (`sai_metrics_indexes`)'
        eval_round_command = '| eval min=round(min,2), max=round(max,2)'
        if not dimensions:
            spl = '%s BY metric_name %s' % (mstats_base_command, eval_round_command)
        else:
            filter_fields = []
            for dim_name, dim_values in dimensions.items():
                # First add double quotes to each dimension value
                dimensions[dim_name] = ['"{}"'.format(val) for val in dim_values]
                # Values of the same dimension name should be "OR"
                filter_fields.append(
                    ' OR '.join('{0}={1}'.format(*dim_pair) for dim_pair in zip(
                        [dim_name] * len(dim_values),
                        dim_values
                    )))

            # Values between dimension names should be "AND"
            dim_filter = ' AND '.join(['({})'.format(f) for f in filter_fields])
            spl = '%s AND %s BY metric_name %s' % (mstats_base_command, dim_filter, eval_round_command)
        results = self.search(spl, earliest, latest, count)
        res = []
        if 'results' in results and len(results['results']) > 0:
            res = results['results']
            logger.info('Retrieved metric names by dimension names')
        return em_common.always_list(res)

    def get_avg_metric_val_by_entity(self,
                                     execute_search=True,
                                     metric_name='',
                                     entities=[],
                                     collector_config={},
                                     earliest='-24h',
                                     latest='now',
                                     count=0,
                                     collection=EMConstants.STORE_ENTITY_CACHE):
        """
        Get average metric value by entity

        NOTE: This assumes that each entity is associated with a collector.
        For entities without a collector (created via REST), this doesn't return any result.

        The sample generated spl search:

        | mstats avg(cpu.nice) as value WHERE (`sai_metrics_indexes`) BY name
        | eval key=sha256( 'uuid'  + ":" + "vmware_host")
        | append [ | mstats avg(cpu.nice) as value WHERE (`sai_metrics_indexes`) BY host
        | eval key=sha256( 'host'  + ":" + "perfmon") ]

        :param execute_search boolean indicating if search should be executed or only return the generated SPL
        :param metric_name: Selected single metric name to calculate average value for
            i.e. 'cpu.idle'
        :param entities: Entities to calulate metric value from
        :param collector_config: collector name-title mapping.
            Used to map collector name of entities to title dimensions of collectors
        :param earliest: earliest time
        :param latest: latest time
        :param count: limit number of result
        :param collection: kvstore collection to perform lookup against
        :return: [{'key': 'asdasd', 'value': '49.78'},
                  {'key': 'fghfgh', 'value': '48.96'}...]
        """
        if not entities or not collector_config:
            return []
        else:
            base_mstats_cmd = '| mstats avg(%s) as value' % metric_name
            eval_cmd = '  | eval value=round(value,2) '
            cur_collector_name_set = set(
                [list(entity['collectors'][0].values())[0] for entity in entities if 'collectors' in entity]
            )
            # get the set of id dimensions
            collector_config_dict = {collector_name: collector_config[collector_name]
                                     for collector_name in cur_collector_name_set}

            mstats_cmds = []
            for entity_class_key, config_dict in collector_config_dict.items():
                id_dims = config_dict.get('id_dims', [])
                id_dims_concat_comma = ','.join(
                                            ['"{}"'.format(dim) for dim in id_dims]
                                        )
                id_dims_concat_expr = ' + ":" + '.join(
                                            ['\'{}\''.format(dim) for dim in id_dims]
                                        )
                where_clause = 'WHERE (`sai_metrics_indexes`)'
                by_cmd = 'BY %s' % id_dims_concat_comma
                eval_key_cmd = '| eval key=sha256( {id_dims_concat_expr}  + ":" + "{entity_class_key}")'.format(
                                    id_dims_concat_expr=id_dims_concat_expr,
                                    entity_class_key=entity_class_key
                                )
                mstats_for_cur_id_dim = ' '.join([base_mstats_cmd, where_clause, by_cmd, eval_key_cmd])
                complete_spl = ' | '.join([mstats_for_cur_id_dim])
                mstats_cmds.append(complete_spl)

            # Synax reformat - wrap mstats cmd with [] except for the first one
            for idx, cmd in enumerate(mstats_cmds):
                if idx != 0:
                    mstats_cmds[idx] = '[ %s ]' % cmd

            final_spl = ' '.join([' | append '.join(mstats_cmds), eval_cmd])
            if execute_search:
                results = self.search(final_spl, earliest, latest, count)
                res = []
                if 'results' in results and len(results['results']) > 0:
                    res = results['results']
                return res
            else:
                return final_spl

    def filter_groups_by_entity_ids(self,
                                    entity_ids,
                                    earliest='-24h',
                                    latest='now',
                                    count=0):

        spl_template = '| inputlookup %s where %s \
            | %s \
            | stats count by group_id'

        entity_predicate = ' OR '.join(
            ['_key="%s"' % e for e in entity_ids])

        spl = spl_template % (EMConstants.STORE_ENTITY_CACHE,
                              entity_predicate,
                              self.CUSTOM_SEARCH_CMD)
        results = self.search(spl, earliest, latest, count)
        return EMSearchManager.parse_group_entities_count_results(results)

    @staticmethod
    def parse_entities_and_dimensions_in_group(results, group_name):
        res = {
            group_name: {
                'entities_mapping': {},
                'count': len(results['results']),
                'active': 0,
                'inactive': 0,
                'disabled': 0
            }
        }

        for record in results['results']:
            """
            get the key and the identifier dimensions of each entity in the following
            format:
            {xyz:['blah']}
            """
            identifier_dimensions_map = {}
            identifier_dimensions = em_common.always_list(record.get('identifier_dimensions', []))
            for each_id_dim in identifier_dimensions:
                identifier_dimensions_map[each_id_dim] = em_common.always_list(
                    record.get('dimensions.{0}'.format(each_id_dim)))
            res[group_name]['entities_mapping'][record.get('title')] = {
                'key': record.get('key'),
                'identifier_dimensions': identifier_dimensions_map,
                'state': record.get('state'),
            }
            res[group_name][record.get('state')] += 1
        return res

    @staticmethod
    def parse_group_entities_count_results(results):
        res = {}
        if 'results' in results and len(results['results']) > 0:
            for record in results['results']:
                res[record.get('group_id')] = {}
                res[record.get('group_id')]['count'] = int(record.get('count'))
        return res
