import em_path_inject  # noqa
try:
    import http.client as httplib
except ImportError:
    import httplib
import json

import em_common
import em_constants
from em_correlation_filters import serialize
from em_model_entity import EmEntity
from em_model_entity_class import EntityClass
from em_search_manager import EMSearchManager
from logging_utils import log
from rest_handler.exception import BaseRestException

from utils.i18n_py23 import _
from splunk.util import normalizeBoolean

try:
    basestring
except NameError:
    basestring = str

logger = log.getLogger()


class EntityNotFoundException(BaseRestException):
    def __init__(self, msg):
        super(EntityNotFoundException, self).__init__(httplib.NOT_FOUND, msg)


class EntityArgValidationException(BaseRestException):
    def __init__(self, msg):
        super(EntityArgValidationException, self).__init__(httplib.BAD_REQUEST, msg)


class EmEntityInterfaceImpl(object):
    def __init__(self, session_key):
        self.session_key = session_key
        self.search_manager = EMSearchManager(em_common.get_server_uri(), self.session_key, em_constants.APP_NAME)

    def _get_entity_filter_query(self, request):
        query = request.query.get('query', '{}')
        query_dict = None
        try:
            query_dict = json.loads(query)
        except ValueError:
            raise EntityArgValidationException(_('Invalid query format, expected JSON'))
        return query_dict

    def handle_load(self, request):
        count = request.query.get('count', 0)
        offset = request.query.get('offset', 0)
        sort_key = request.query.get('sort_key', '')
        sort_dir = request.query.get('sort_dir', 'asc')
        query_dict = self._get_entity_filter_query(request)
        entities = EmEntity.load(count, offset, sort_key, sort_dir, query_dict)
        return [self.extract_entity_json_response(entity) for entity in entities]

    def handle_get(self, request, key):
        entity = EmEntity.get(key)
        if not entity:
            raise EntityNotFoundException(_('Entity with id %(key)s not found.'))

        correlation_filter = entity.get_correlation_filter()
        response = self.extract_entity_json_response(entity)
        response.update({
            'correlation_filter': serialize(correlation_filter)
        })
        return response

    def handle_delete(self, request, key):
        query = {'_key': [key]}
        EmEntity.bulk_delete(query)

    def handle_bulk_delete(self, request):
        query = self._get_entity_filter_query(request)
        exclusion_list = json.loads(request.query.get('exclusion_list', '[]'))
        EmEntity.bulk_delete(query, exclusion_list=exclusion_list)

    def handle_metadata(self, request):
        query_dict = self._get_entity_filter_query(request)
        metadata = EmEntity.get_metadata(query_dict)
        return metadata

    def handle_dimension_summary(self, request):
        query_dict = self._get_entity_filter_query(request)
        dim_summary = EmEntity.get_dimension_summary(query_dict)
        return {'dimensions': dim_summary}

    def handle_metric_names(self, request):
        count = request.query.get('count', 0)
        query = request.query.get('query')
        if query:
            query = self._load_valid_metric_names_query_param(query)
        results_list = self.search_manager.get_metric_names_by_dim_names(dimensions=query, count=count)
        metrics_list = [{em_constants.DEFAULT_METRIC_FOR_COLOR_BY: {'min': '0.00', 'max': '1.00'}}]
        if results_list:
            for r in results_list:
                metrics_list.append({
                    r.get('metric_name'): {'min': r.get('min'), 'max': r.get('max')}
                })
        return metrics_list

    def handle_metric_data(self, request):
        count = request.query.get('count', 0)
        query = request.query.get('query', '')
        if not query:
            raise EntityArgValidationException(_('Missing required query parameter: query'))
        query_params = self._load_valid_metric_data_query(query)
        dimensions = query_params.get('dimensions', {})
        dimensions = {'dimensions.{}'.format(key): value for key, value in dimensions.items()}

        # retrieve filtered entities and transform it for get_avg_metric_val_by_entity()
        filtered_entities = EmEntity.load(count, 0, '', 'asc', dimensions)
        filtered_entities = [
            {"key": entity.key,
             "collectors": [{"name": entity.entity_class}],
             "dimensions": {dim_key: dim_val
                            for (dim_key, dim_vals) in entity.dimensions.items()
                            for dim_val in dim_vals}}
            for entity in filtered_entities]

        # get entity class map of key to title dimension
        entity_classes = EntityClass.load()

        collectors_map = {ec.key: {'title_dim': ec.title_dimension, 'id_dims': ec.identifier_dimensions}
                          for ec in entity_classes}

        # run search
        should_execute_search = normalizeBoolean(query_params.get('executeSearch', True))
        search_res = self.search_manager.get_avg_metric_val_by_entity(execute_search=should_execute_search,
                                                                      metric_name=query_params['metric_name'],
                                                                      entities=filtered_entities,
                                                                      collector_config=collectors_map,
                                                                      count=count,
                                                                      collection=em_constants.STORE_ENTITY_CACHE)
        response = {
            res.get('key'): res.get('value') for res in search_res
        } if isinstance(search_res, list) else search_res
        return response

    @staticmethod
    def extract_entity_json_response(entity):
        id_dims, info_dims = {}, {}
        for dim, val in entity.dimensions.items():
            if dim in entity.identifier_dimension_names:
                id_dims[dim] = val
            else:
                info_dims[dim] = val
        entity_class = entity.get_entity_class_info()
        dimension_display_names = em_common.get_locale_specific_display_names(entity_class.dimension_display_names)
        return {
            '_key': entity.key,
            'title': entity.title,
            'entity_class': entity.entity_class,
            'mod_time': entity.mod_time,
            'expiry_time': entity.expiry_time,
            'status': entity.status,
            'identifier_dimensions': id_dims,
            'informational_dimensions': info_dims,
            'vital_metrics': entity_class.vital_metrics,
            'dimension_display_names': dimension_display_names
        }

    def _load_valid_metric_names_query_param(self, query_param):
        """
        Query params are expected to be a dictionary with dimension name as key, list of dimension values as value
        """
        message = _(
            'Cannot parse query parameter. Expected format is {<dimension name>: '
            '[ <dimension values, wildcards>]}'
        )
        # Check if it's a valid json string
        try:
            query_param = json.loads(query_param)
        except Exception as e:
            logger.error('Failed to parse query parameters - query: %s, error: %s' % (query_param, e))
            raise EntityArgValidationException(message)
        if isinstance(query_param, dict):
            # Check if key is string and value is list
            is_query_param_valid = all(
                isinstance(key, basestring) and isinstance(value, list) for (key, value) in query_param.items())
            if is_query_param_valid is False:
                raise EntityArgValidationException(message)
        else:
            raise EntityArgValidationException(message)
        return query_param

    def _load_valid_metric_data_query(self, query_param):
        # {metric_name:cpu.idle, dimensions:{os:["ubuntu"]}}
        message = _(
            'Cannot parse query parameter. Expected format is {metric_name: <metric_name>, '
            'dimensions: {<dimension name>: [<dimension values, wildcards>]}}'
        )
        # Check if it's a valid json string
        try:
            query_param = json.loads(query_param)
        except Exception as e:
            logger.error('Failed to parse query parameters - query: %s, error: %s' % (query_param, e))
            raise EntityArgValidationException(message)
        if isinstance(query_param, dict):
            # Check if both metric_name and dimensions exist
            if 'metric_name' not in query_param:
                raise EntityArgValidationException(_('Missing required key: metric_name'))
            metric_name = query_param['metric_name']
            dimensions = query_param.get('dimensions')
            # Check type for required key - metric_name
            if not isinstance(metric_name, basestring):
                raise EntityArgValidationException(_('Expected metric name to be a string.'))
            if dimensions:
                self._validate_dimensions_query(dimensions)
        else:
            raise EntityArgValidationException(_('Expected query param to be a dict'))
        return query_param

    def _validate_dimensions_query(self, dimensions):
        # Check type for dimensions
        if not isinstance(dimensions, dict):
            raise EntityArgValidationException(_('Expected dimensions to be a dict.'))
        # Check if each key in dimensions is a string and each value is a list
        is_query_param_valid = all(
            isinstance(key, basestring) and isinstance(value, list) for (key, value) in dimensions.items())
        if is_query_param_valid is False:
            raise EntityArgValidationException(
                _('Expected each key in dimensions to be a string, each value to be a list')
            )
