"""
This provides some functions for accessing and managing lookup file backups.
"""

import os
import shutil
import time
import datetime

from splunk.clilib.bundle_paths import make_splunkhome_path

from lookup_editor.lookupfiles import SplunkLookupTableFile
from lookup_editor.shortcuts import escape_filename
from lookup_editor.exceptions import PermissionDeniedException

class LookupBackups(object):
    """
    This class provides functions for managing backup files. It is bundled in an instantiable class
    so that it can be given a logger.
    """

    def __init__(self, logger):
        if logger is None:
            raise Exception("Logger must not be none")
        else:
            self.logger = logger

    def get_backup_files(self, session_key, lookup_file, namespace, owner):
        """
        Get a list of backup files for a given file
        """

        # Escape the file name so that we find the correct file
        escaped_filename = escape_filename(lookup_file)

        # Get the backup directory and determine the path to the backups
        backup_directory = self.get_backup_directory(session_key, escaped_filename, namespace, owner)

        # Get the backups
        backups = [f for f in os.listdir(backup_directory) if os.path.isfile(os.path.join(backup_directory, f))]

        return backups

    def get_lookup_backups_list(self, session_key, lookup_file, namespace, owner=None):
        """
        Get a list of the lookup file backups rendered as JSON.
        """

        backups = self.get_backup_files(session_key, lookup_file, namespace, owner)

        # Make the response
        backups_meta = []

        for backup in backups:
            try:
                backups_meta.append(
                    {
                        'time': backup,
                        'time_readable' : datetime.datetime.fromtimestamp(float(backup)).strftime('%Y-%m-%d %H:%M:%S')
                    }
                )
            except ValueError:
                self.logger.warning("Backup file name is invalid, file_name=%s", backup)

        # Sort the list
        backups_meta = sorted(backups_meta, key=lambda x: float(x['time']), reverse=True)

        return backups_meta

    def get_backup_directory(self, session_key, lookup_file, namespace, owner=None, resolved_lookup_path=None):
        """
        Get the backup directory where the lookup should be stored
        """

        if owner is None:
            owner = 'nobody'

        # Identify the current path of the given lookup file
        if resolved_lookup_path is None:
            resolved_lookup_path = SplunkLookupTableFile.get(SplunkLookupTableFile.build_id(lookup_file, namespace, owner), sessionKey=session_key).path

        # Determine what the backup directory should be
        backup_directory = make_splunkhome_path([os.path.dirname(resolved_lookup_path),
                                                 "lookup_file_backups", namespace, owner,
                                                 escape_filename(lookup_file)])

        # Make the backup directory, if necessary
        if not os.path.exists(backup_directory):
            os.makedirs(backup_directory)

        return backup_directory

    def backup_lookup_file(self, session_key, lookup_file, namespace, resolved_file_path, owner=None, file_save_time=None):
        """
        Make a backup if the lookup file.
        """

        try:

            # Get the backup directory
            backup_directory = self.get_backup_directory(session_key, lookup_file, namespace, 
                                                         owner, resolved_file_path)

            # Get the modification time of the existing file so that we put the date as an epoch
            # in the name
            try:
                file_time = os.path.getmtime(resolved_file_path)
            except:
                self.logger.warning('Unable to get the file modification time for the existing lookup file="%s"', resolved_file_path)
                file_time = None

            # If we got the time for backup file, then use that time
            # This is important because the times ought to be consistent between search heads in a
            # cluster
            if file_save_time is not None:
                file_time = file_save_time
            
            # If we couldn't get the time, then just use the current time (the time we are making
            # a backup)
            if file_time is None:
                file_time = time.time()

            # Make the full paths for the backup to be stored
            dst = make_splunkhome_path([backup_directory, str(file_time)])

            # Make the backup
            shutil.copyfile(resolved_file_path, dst)

            # Copy the permissions and timestamps
            shutil.copystat(resolved_file_path, dst)

            self.logger.info('A backup of the lookup file was created, namespace=%s, lookup_file="%s", backup_file="%s"', namespace, lookup_file, dst)

            # Return the path of the backup in case the caller wants to do something with it
            return dst
        except:
            self.logger.exception("Error when attempting to make a backup; the backup will not be made")

            return None
