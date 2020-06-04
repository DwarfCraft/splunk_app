[<entity class name>]
title = <string>
* Title of the entity class

type = <metric|event|csv>
* Type of entity class that determines from which kind of data will the entities be discovered.
* Allowed values are "metric", "event" or "csv"

source_filter = <string>
* Filter for discovering data from a dataset filtered down to a smaller scope.
* e.g. metric_name=cpu.* AND index=em_metrics

title_dimension = <string>
* Dimension whose value from the dataset becomes the title of entity.

identifier_dimensions = <list of strings>
* A list of dimensions that can be used to uniquely identify an entity within the entity class.

informational_dimensions = <"*" or list of strings>
* A list of dimensions that describes the attributes of discovered entities.

blacklisted_dimensions = <list of strings>
* A list of dimensions that should be excluded from discovered entities.

monitoring_window = <integer>
* Time range (specified with number of seconds to look back) of data that is used to discover entities

cron_schedule = <string>
* Schedule of the entity class discovery search.
* If not set, default to the every number of minutes derived from the monitoring window.
* e.g. If monitoring_window = 60, then cron_schedule = */1 * * * *

status_transform = <string>

retirement_policy = <string>

correlation_rules = <json>
* Correlation rules that are used to construct event log filter of an entity to find related log events.
* Example:
'unix_logs': {
    # base search is used as a first pass filer to find events
    # correlated to this collector -- eg. sourcetype=syslog
    'base_search': {
        # a *Boolean filter*, takes a boolean operator and a list of filters
        # (matching BooleanFilter class in em_correlation_filters)
        'type': 'or',
        'filters': [
            {
                # a *Basic filter*, takes a type, field and values
                # (matching BasicFilter class in em_correlation_filters)
                'type': 'include',
                'field': 'sourcetype',
                'values': ['*']
            }
        ]
    },
    # Entity filters are used to correlate between metrics and logs
    # by searching for logs whose value of event_field is the value of dimension_name
    # in metrics data -- eg. host=alabama.usa.com
    'entity_filters': {
        'type': 'or',
        'filters': [
            {
                # an *Entity filter*, takes a event_field and dimension_name
                # (matching EntityFilter class in em_correlation_filters)
                'event_field': 'host',
                'dimension_name': 'host'
            }
        ]
    }
}

vital_metrics =  <json>
* Default metrics that are important to this entity class
* Also used to display default panels on the Entity Analysis Workspace page.
* Example: ["cpu.system", "memory.free"]

dimension_display_names = <json>
* An array of dimensions with values in a human-readable format in different locations.
* Example: 
[
    "os": {"en-US": "OS", "zh-CN": "操作系统"},
    "os_version": {"en-US": "Version", "zh-CN": "版本"}
]