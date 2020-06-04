from future.moves.urllib.parse import quote
from logging_utils import log

# set up logger
logger = log.getLogger()


def get_conf_stanza(conf_manager, file_name):
    try:
        return conf_manager.get_conf(file_name)
    except Exception as e:
        logger.error(file_name + ' conf file was not located in local or default folders')
        logger.error(e)
        raise e


def get_check_internal_log_message():
    query = quote('search index=_internal sourcetype="splunk_app_infrastructure"')
    return ('[[/app/splunk_app_infrastructure/search?q=%s|'
            'SAI internal logs.]]') % query


def is_lower_version(version_left, version_right):
    """
    Test whether version_right is a higher version than version_left
    """
    exception_string = "Unknown version number encountered in version comparison"

    def numberify_version(version_string):
        rv = version_string.split(".")
        for i in range(len(rv)):
            try:
                rv[i] = int(rv[i])
                if (rv[i] < 0):
                    raise Exception(exception_string)
            except ValueError:
                # If this is a string like "beta" or something else, we fill it with a dummy value
                # which may not end up being used in comparison (e.g. "1.0.0" vs "2.0.0-beta")
                rv[i] = -1
        return rv

    if version_left == version_right:
        return False
    version_left = numberify_version(version_left)
    version_right = numberify_version(version_right)
    # Normalize lengths
    length_difference = len(version_left) - len(version_right)
    shorter_version = None
    if (length_difference > 0):
        shorter_version = version_right
    elif (length_difference < 0):
        shorter_version = version_left
    if shorter_version:
        for i in range(abs(length_difference)):
            shorter_version.append(0)
    for i in range(len(version_left)):
        if version_left[i] == -1 or version_right[i] == -1:
            raise Exception(exception_string)
        if version_left[i] > version_right[i]:
            return False
        elif version_left[i] < version_right[i]:
            return True
    return False
