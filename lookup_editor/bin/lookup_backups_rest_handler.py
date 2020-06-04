"""
This controller provides helper methods to the front-end views that manage lookup files.
"""

import logging
import csv
import time

from splunk.clilib.bundle_paths import make_splunkhome_path
from splunk import AuthorizationFailed, ResourceNotFound

# The default of the csv module is 128KB; upping to 10MB. See SPL-12117 for
# the background on issues surrounding field sizes.
# (this method is new in python 2.5)
csv.field_size_limit(10485760)

def setup_logger(level):
    """
    Setup a logger for the REST handler
    """

    logger = logging.getLogger('splunk.appserver.lookup_backups.rest_handler')
    logger.propagate = False # Prevent the log messages from being duplicated in the python.log file
    logger.setLevel(level)

    log_file_path = make_splunkhome_path(['var', 'log', 'splunk', 'lookup_backups_rest_handler.log'])
    file_handler = logging.handlers.RotatingFileHandler(log_file_path, maxBytes=25000000,
                                                        backupCount=5)

    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger

logger = setup_logger(logging.DEBUG)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lookup_editor import LookupEditor
from lookup_editor import rest_handler

class LookupBackupsHandler(rest_handler.RESTHandler):
    """
    This is a REST handler that supports backing up lookup files.

    This is broken out as a separate handler so that this handler can be replayed on other search
    heads via the allowRestReplay setting in restmap.conf.
    """

    def __init__(self, command_line, command_arg):
        super(LookupBackupsHandler, self).__init__(command_line, command_arg, logger)

        self.lookup_editor = LookupEditor(logger)

    def post_backup(self, request_info, lookup_file=None, namespace="lookup_editor",
                    owner=None, file_time=None, **kwargs):
        """
        Make a backup of the given lookup file.
        """

        try:
            # Determine the final path of the file
            resolved_file_path = self.lookup_editor.resolve_lookup_filename(lookup_file,
                                                                            namespace,
                                                                            owner,
                                                                            session_key=request_info.session_key,
                                                                            throw_not_found=True)

            # Backup the file passing the time so that the REST handler will use the same time for
            # all lookups even when the REST call is being replayed in an SHC cluster
            file_path = self.lookup_editor.backup_lookup_file(request_info.session_key,
                                                              lookup_file, namespace,
                                                              resolved_file_path, owner,
                                                              file_time)

            self.logger.info("Created a backup of a lookup file, file_path=%s", file_path)

            # Everything worked, return accordingly
            return {
                'payload': str(file_path), # Payload of the request.
                'status': 200 # HTTP status code
            }

        except ResourceNotFound:

            self.logger.warn("Unable to find the lookup to backup")

            return self.render_error_json("Unable to find the lookup to backup", 404)

        except:

            self.logger.exception("Exception generated when attempting to backup a lookup file")
            return self.render_error_json("Unable to backup the lookup")
