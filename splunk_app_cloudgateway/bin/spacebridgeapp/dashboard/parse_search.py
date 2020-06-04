"""
(C) 2019 Splunk Inc. All rights reserved.

Parse functions for search
"""

from spacebridgeapp.data.search_job_data import SearchJobContent, Message
from spacebridgeapp.data.saved_search_data import SavedSearch, SavedSearchHistory
from spacebridgeapp.data.dispatch_state import DispatchState


def to_search_job_content(json_object):
    """
    Parse a Search Job Entry json into and return a SearchJobContent
    :param json_object:
    :return:
    """
    if json_object is not None and isinstance(json_object, dict):
        content = json_object.get('content')

        if content:
            search_id = get_string_field('sid', content)
            is_done = get_boolean_field('isDone', content)
            dispatch_state = DispatchState.from_string(get_string_field('dispatchState', content)).value
            done_progress = get_float_field('doneProgress', content)
            earliest_time = get_string_field('earliestTime', content)
            latest_time = get_string_field('latestTime', content)
            sample_ratio = get_string_field('sampleRatio', content)
            result_count = get_string_field('resultCount', content)
            report_search = get_string_field('reportSearch', content)

            # parse messages object
            messages = []
            messages_object = content.get('messages')
            if messages_object:
                messages = [to_message(message) for message in messages_object]

            return SearchJobContent(sid=search_id,
                                    is_done=is_done,
                                    dispatch_state=dispatch_state,
                                    done_progress=done_progress,
                                    earliest_time=earliest_time,
                                    latest_time=latest_time,
                                    sample_ratio=sample_ratio,
                                    result_count=result_count,
                                    report_search=report_search,
                                    messages=messages)

    return SearchJobContent()


def to_message(message_object):
    """
    Parse a Message object
    :param message_object:
    :return:
    """
    if message_object is not None and isinstance(message_object, dict):
        message_type = get_string_field('type', message_object)
        text = get_string_field('text', message_object)

        return Message(type=message_type, text=text)
    return Message()


def to_saved_search(json_object):
    """
    Parse a Saved Search Entry json and return a SavedSearch
    :param json_object:
    :return:
    """
    if json_object is not None and isinstance(json_object, dict):
        name = get_string_field('name', json_object)
        content = json_object.get('content')
        if content:
            is_scheduled = get_boolean_field('is_scheduled', content)
            search = get_string_field('search', content)
            visualization_type = get_string_field('display.visualizations.type', content)
            options_map = get_saved_search_options_map(content, visualization_type)
            return SavedSearch(name=name, is_scheduled=is_scheduled, search=search,
                               visualization_type=visualization_type, options_map=options_map)
    return SavedSearch()


def get_saved_search_options_map(content, visualization_type):
    """
    Helper method to translate option in saved search meta to an options map
    :param content:
    :param visualization_type:
    :return:
    """
    options_map = {}
    if content is not None and isinstance(content, dict) and visualization_type:
        display_visualizations_prefix = 'display.visualizations'
        type_prefix = display_visualizations_prefix + '.' + visualization_type
        trellis_prefix = display_visualizations_prefix + '.trellis'
        for key, value in content.iteritems():
            if key.startswith(type_prefix) or key.startswith(trellis_prefix):
                # For some reason singlevalue options aren't prefixed so we need to remove
                if visualization_type == 'singlevalue':
                    options_map[key[len(type_prefix) + 1:]] = value
                else:
                    options_map[key[len(display_visualizations_prefix) + 1:]] = value
    return options_map


def to_saved_search_history(json_object):
    """
    Parse a Saved Search History Entry json and return a SavedSearchHistory
    :param json_object:
    :return:
    """
    if json_object is not None and isinstance(json_object, dict):
        name = get_string_field('name', json_object)
        content = json_object.get('content')
        if content:
            is_scheduled = get_boolean_field('isScheduled', content)
            is_done = get_boolean_field('isDone', content)
            return SavedSearchHistory(name=name, is_scheduled=is_scheduled, is_done=is_done)
    return SavedSearchHistory()


def get_string_field(field, dictionary, default=''):
    """
    Helper method to get string_field
    :param field:
    :param dictionary:
    :param default:
    :return:
    """
    if field in dictionary:
        s = dictionary[field]
        return default if s is None else str(s)
    return default


def get_boolean_field(field, dictionary, default=False):
    """
    Helper method to get boolean_field
    :param field:
    :param dictionary:
    :param default:
    :return:
    """
    if field in dictionary:
        s = dictionary[field]
        return default if s is None else s
    return default


def get_float_field(field, dictionary, default=0.0):
    """
    Helper method to get float_field
    :param field:
    :param dictionary:
    :param default:
    :return:
    """
    if field in dictionary:
        s = dictionary[field]
        return default if s is None else float(s)
    return default
