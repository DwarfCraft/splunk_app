import logging
import logging.handlers
from splunk import setupSplunkLogger
from splunk.clilib.bundle_paths import make_splunkhome_path
import os
import sys

try:
    basestring
except NameError:
    basestring = str

'''
In order to use a logger in SAI call the getLogger method.
If no logger_name is provided, it will determine the entry point of the process and log to
$SPLUNK_HOME/var/log/splunk/sai_<process_name>.log

Example usage:
>>>from logging_utils import log
>>>logger = log.getLogger()
>>>logger.critical('test error message')
'''

DEFAULT_LOGGING_FORMAT = '%(asctime)s - pid:%(process)d tid:%(threadName)s \
%(levelname)-s  %(module)s:%(lineno)d - %(message)s'
DEFAULT_MAX_FILE_SIZE = 25*1024*1024  # 25 MB log size before rollover
DEFAULT_LOG_FILE_PREFIX = 'sai'
# To change logging level globally for debugging purposes, change this to logging.DEBUG
DEFAULT_LOG_LEVEL = logging.INFO
REST_STARTING_PROCESS_NAME = 'appserver'
REST_LOGGER_NAME = 'rest_audit'


def getLogger(logger_name=None, logfile_name=None, log_level=None, log_format=DEFAULT_LOGGING_FORMAT):
    '''
    Returns a Python standard library logger setup for logging in SAI.

    :param logger_name - logger name
    :param logfile_name - log file name (NOT the entire path)
    :param log_level - logging level
    :param log_format - log message format
    return: logger
    '''
    if logger_name is None:
        logger_name = _get_logger_name()
    logger_name = _format_logger_name(logger_name)
    if logfile_name is None:
        logfile_name = logger_name + '.log'
    return _setup_logging(logger_name=logger_name,
                          logfile_name=logfile_name,
                          log_level=log_level,
                          log_format=log_format)


def _setup_logging(logger_name, logfile_name, log_level=None, log_format=DEFAULT_LOGGING_FORMAT):
    '''
    Setup a logger. In order to setup a logger from an external program, do not call this, call getLogger instead.

    :param logger_name - logger name
    :param logfile_name - log file name (NOT the entire path)
    :param log_level - logging level
    :param log_format - log message format
    return: logger completely setup
    '''
    # Python's loggging is singleton so if a logger is already defined it will return old handlers
    logger = logging.getLogger(logger_name)

    logger = _setup_logging_file_handler(logger, logfile_name, log_format)
    logger.propagate = False  # Prevent some log messages from being duplicated in splunkd.log
    if log_level is None:
        logger.setLevel(DEFAULT_LOG_LEVEL)
        logger = _setup_logging_splunk_configs(logger)
    else:
        logger.setLevel(parse_log_level(log_level))
    return logger


def _setup_logging_file_handler(logger, logfile_name, log_format):
    '''
    Setup the loggers file handler
    If handler is already defined then do not create new handler to avoid opening the file again

    :param logger - the logger
    :param logfile_name - log file name (NOT the entire path)
    :param log_format - log message format
    :return the logger with file handlers setup
    '''
    has_file_handler = False
    for handler in logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            has_file_handler = True

    if not has_file_handler:
        base_log_dir = make_splunkhome_path(['var', 'log', 'splunk'])
        if not os.path.exists(base_log_dir):
            os.makedirs(base_log_dir)
        logfile_path = os.path.join(base_log_dir, logfile_name)

        file_handler = logging.handlers.RotatingFileHandler(
            logfile_path,
            mode='a',
            maxBytes=DEFAULT_MAX_FILE_SIZE,
            backupCount=5)
        file_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(file_handler)
    return logger


def _setup_logging_splunk_configs(logger):
    '''
    Read logging level information from config files to overwrite log level

    :param logger - the logger
    :return the logger with logging level overwritten
    '''
    logging_default_config_file = make_splunkhome_path(['etc', 'log.cfg'])
    logging_local_config_file = make_splunkhome_path(['etc', 'log-local.cfg'])
    logging_stanza_name = 'python'
    setupSplunkLogger(
        logger,
        logging_default_config_file,
        logging_local_config_file,
        logging_stanza_name,
        verbose=False)
    return logger


def _get_logger_name():
    '''
    Creates a logger name if name is not supplied
    '''
    logger_name = os.path.basename(sys.argv[0])[:-len('.py')]
    # All REST implementation files are started by appserver.py
    if logger_name == REST_STARTING_PROCESS_NAME:
        return REST_LOGGER_NAME
    return logger_name


def _format_logger_name(logger_name):
    '''
    Makes sure logger name is properly formatted (starts with sai_)
    '''
    if logger_name.startswith('em_'):
        logger_name = DEFAULT_LOG_FILE_PREFIX + '_' + logger_name[3:]
    elif not logger_name.startswith(DEFAULT_LOG_FILE_PREFIX):
        logger_name = DEFAULT_LOG_FILE_PREFIX + '_' + logger_name
    return logger_name


def parse_log_level(log_level):
    '''
    Convert log_level in string format into its corresponding integer value defined in
    the `logging` module. NOTE: this function should only be used when calling `setLevel` of `logging`
    module with the python2.7 interpreter. In python3, `setLevel` supports log level in string format directly

    :param log_level - log level string, e.g. "WARNING", "DEBUG"
    :return log level integer value
    '''
    if not isinstance(log_level, basestring):
        return log_level

    level_map = {
        'NOTSET': logging.NOTSET,
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'WARN': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    return level_map.get(log_level.upper(), DEFAULT_LOG_LEVEL)
