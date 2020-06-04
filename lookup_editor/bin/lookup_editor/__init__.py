"""
This module includes the main functions for editing lookup files. This class serves as an entry
point to the rest of the related lookup editing modules. The REST handler and/or controller
shouldn't need to call functions in the dependencies.
"""

import os
import io
import json
import shutil
import csv
from collections import OrderedDict

from splunk.rest import simpleRequest
from splunk import AuthorizationFailed, ResourceNotFound
from splunk.clilib.bundle_paths import make_splunkhome_path

from lookup_editor.lookup_backups import LookupBackups
from lookup_editor.exceptions import LookupFileTooBigException, PermissionDeniedException, LookupNameInvalidException
from lookup_editor.shortcuts import flatten_dict, is_file_name_valid, is_lookup_in_users_path, make_lookup_filename
from lookup_editor import lookupfiles
from lookup_editor import settings

class LookupEditor(LookupBackups):
    """
    This class provides functions for editing lookup files. It is bundled in an instantiable class
    so that it can be given a logger.

    This class inherits from LookupBackups in order to be able to leverage the .
    """

    def __init__(self, logger):
        super(LookupEditor, self).__init__(logger)

    def get_kv_fields_from_transform(self, session_key, collection_name, namespace="lookup_editor", owner=None):
        """
        Get the list of fields for the given lookup from the transform.
        """

        response, content = simpleRequest('/servicesNS/nobody/' + namespace +
                                          '/data/transforms/lookups',
                                          sessionKey=session_key,
                                          getargs={
                                              'output_mode': 'json',
                                              'search': 'collection=' + collection_name
                                          })

        # Make sure we found something
        if response.status < 200 or response.status > 300:
            return None

        # Parse the output
        transforms = json.loads(content, object_pairs_hook=OrderedDict)
        transform = None

        # Make sure we got entries
        if len(transforms['entry']) == 0:
            return None
        else:
            transform = transforms['entry'][0]
    
        # If we got a match, then get the fields
        if transform is not None and 'content' in transform and 'fields_array' in transform['content']:
            return transform['content']['fields_array']
        else:
            return None

    def get_kv_lookup(self, session_key, lookup_file, namespace="lookup_editor", owner=None):
        """
        Get the contents of a KV store lookup.
        """

        if owner is None:
            owner = 'nobody'

        lookup_contents = []

        # Get the fields so that we can compose the header
        # Note: this call must be done with the user context of "nobody".
        response, content = simpleRequest('/servicesNS/nobody/' + namespace +
                                          '/storage/collections/config/' +
                                          lookup_file,
                                          sessionKey=session_key,
                                          getargs={'output_mode': 'json'})

        if response.status == 403:
            raise PermissionDeniedException("You do not have permission to view this lookup")

        header = json.loads(content, object_pairs_hook=OrderedDict)

        fields = ['_key']

        for field in header['entry'][0]['content']:
            if field.startswith('field.'):
                fields.append(field[6:])

        # If we couldn't get fields from the collections config, try to get it from transforms.conf
        if len(fields) <= 1:
            fields = self.get_kv_fields_from_transform(session_key, lookup_file, namespace, owner)

            # See if we got the fields from the transform. If we didn't, then just assume the _key field exists
            if fields is None:
                self.logger.info('Unable to get the fields list from lookup transforms', fields)
                fields = ['_key']
            else:
                self.logger.info('Got fields list from the transform, fields=%r', fields)

        # Add the fields as the first row
        lookup_contents.append(fields)

        # Get the contents
        response, content = simpleRequest('/servicesNS/' + owner + '/' + namespace +
                                          '/storage/collections/data/' + lookup_file,
                                          sessionKey=session_key,
                                          getargs={'output_mode': 'json'})

        if response.status == 403:
            raise PermissionDeniedException("You do not have permission to view this lookup")

        rows = json.loads(content, object_pairs_hook=OrderedDict)

        for row in rows:
            new_row = []

            # Convert the JSON style format of the row and convert it down to chunk of text
            flattened_row = flatten_dict(row, fields=fields)

            # Add each field to the table row
            for field in fields:

                # If the field was found, add it
                if field in flattened_row:
                    new_row.append(flattened_row[field])

                # If the field wasn't found, add a blank string. We need to do this to make
                # sure that the number of columns is consistent. We can't have fewer data
                # columns than we do header columns. Otherwise, the header won't line up with
                # the field since the number of columns items in the header won't match the
                # number of columns in the rows.
                else:
                    new_row.append("")

            lookup_contents.append(new_row)

        return lookup_contents

    def get_lookup(self, session_key, lookup_file, namespace="lookup_editor", owner=None,
                   get_default_csv=True, version=None, throw_exception_if_too_big=False):
        """
        Get a file handle to the associated lookup file.
        """

        self.logger.debug("Version is:" + str(version))

        # Check capabilities
        #LookupEditor.check_capabilities(lookup_file, user, session_key)

        # Get the file path
        file_path = self.resolve_lookup_filename(lookup_file, namespace, owner, get_default_csv,
                                                 version, session_key=session_key)

        if throw_exception_if_too_big:

            try:
                file_size = os.path.getsize(file_path)

                self.logger.info('Size of lookup file determined, file_size=%s, path=%s',
                                 file_size, file_path)

                if file_size > settings.MAXIMUM_EDITABLE_SIZE:
                    raise LookupFileTooBigException(file_size)

            except os.error:
                self.logger.exception("Exception generated when attempting to determine size of " +
                                      "requested lookup file")

        self.logger.info("Loading lookup file from path=%s", file_path)

        # Get the file handle
        # Note that we are assuming that the file is in UTF-8. Any characters that don't match
        # will be replaced.
        return io.open(file_path, 'r', encoding='utf-8', errors='replace')


    def resolve_lookup_filename(self, lookup_file, namespace="lookup_editor", owner=None,
                                get_default_csv=True, version=None, throw_not_found=True,
                                session_key=None):
        """
        Resolve the lookup filename. This function will handle things such as:
         * Returning the default lookup file if requested
         * Returning the path to a particular version of a file

        Note that the lookup file must have an existing lookup file entry for this to return
        correctly; this shouldn't be used for determining the path of a new file.
        """

        # Strip out invalid characters like ".." so that this cannot be used to conduct a
        # directory traversal attack
        lookup_file = os.path.basename(lookup_file)
        namespace = os.path.basename(namespace)

        if owner is not None:
            owner = os.path.basename(owner)

        # Assign a default for the user to 'nobody' if not provided
        if owner is None:
            owner = 'nobody'

        # Determine the lookup path by asking Splunk
        try:
            resolved_lookup_path = lookupfiles.SplunkLookupTableFile.get(lookupfiles.SplunkLookupTableFile.build_id(lookup_file, namespace, owner), sessionKey=session_key).path
        except ResourceNotFound:
            if throw_not_found:
                raise
            else:
                return None

        # Get the backup file for one with an owner
        if version is not None and owner not in [None, 'nobody']:
            lookup_path = make_splunkhome_path([self.get_backup_directory(session_key, lookup_file, namespace, owner, resolved_lookup_path=resolved_lookup_path), version])
            lookup_path_default = make_splunkhome_path(["etc", "users", owner, namespace,
                                                        "lookups", lookup_file + ".default"])

        # Get the backup file for one without an owner
        elif version is not None:
            lookup_path = make_splunkhome_path([self.get_backup_directory(session_key, lookup_file, namespace, owner, resolved_lookup_path=resolved_lookup_path), version])
            lookup_path_default = make_splunkhome_path(["etc", "apps", namespace, "lookups",
                                                        lookup_file + ".default"])

        # Get the user lookup
        elif owner not in [None, 'nobody']:
            # e.g. $SPLUNK_HOME/etc/users/luke/SA-NetworkProtection/lookups/test.csv
            lookup_path = resolved_lookup_path
            lookup_path_default = make_splunkhome_path(["etc", "users", owner, namespace,
                                                        "lookups", lookup_file + ".default"])

        # Get the non-user lookup
        else:
            lookup_path = resolved_lookup_path
            lookup_path_default = make_splunkhome_path(["etc", "apps", namespace, "lookups",
                                                        lookup_file + ".default"])

        self.logger.info('Resolved lookup file, path=%s', lookup_path)

        # Get the file path
        if get_default_csv and not os.path.exists(lookup_path) and os.path.exists(lookup_path_default):
            return lookup_path_default
        else:
            return lookup_path

    def is_empty(self, row):
        """
        Determines if the given row in a lookup is empty. This is done in order to prune rows that
        are empty.
        """

        for entry in row:
            if entry is not None and len(entry.strip()) > 0:
                return False

        return True

    def force_lookup_replication(self, app, filename, session_key, base_uri=None):
        """
        Force replication of a lookup table in a Search Head Cluster.
        """

        # Permit override of base URI in order to target a remote server.
        endpoint = '/services/replication/configuration/lookup-update-notify'

        if base_uri:
            repl_uri = base_uri + endpoint
        else:
            repl_uri = endpoint

        # Provide the data that describes the lookup
        payload = {
            'app': app,
            'filename': os.path.basename(filename),
            'user': 'nobody'
        }

        # Perform the request
        response, content = simpleRequest(repl_uri,
                                          method='POST',
                                          postargs=payload,
                                          sessionKey=session_key,
                                          raiseAllErrors=False)

        # Analyze the response
        if response.status == 400:
            if 'No local ConfRepo registered' in content:
                # search head clustering not enabled
                self.logger.info('Lookup table replication not applicable for %s: clustering not enabled',
                                 filename)

                return (True, response.status, content)

            elif 'Could not find lookup_table_file' in content:
                self.logger.error('Lookup table replication failed for %s: status_code="%s", content="%s"',
                                  filename, response.status, content)

                return (False, response.status, content)

            else:
                # Previously unforeseen 400 error.
                self.logger.error('Lookup table replication failed for %s: status_code="%s", content="%s"',
                                  filename, response.status, content)

                return (False, response.status, content)

        elif response.status != 200:
            return (False, response.status, content)

        # Return a default response
        self.logger.info('Lookup table replication forced for %s', filename)
        return (True, response.status, content)

    def update(self, contents=None, lookup_file=None, namespace="lookup_editor", owner=None,
               session_key=None, user=None):
        """
        Update the given lookup file with the provided contents.
        """

        if owner is None:
            owner = "nobody"

        if namespace is None:
            namespace = "lookup_editor"

        # Check capabilities
        #LookupEditor.check_capabilities(lookup_file, request_info.user, request_info.session_key)

        # Ensure that the file name is valid
        if not is_file_name_valid(lookup_file):
            raise LookupNameInvalidException("The lookup filename contains disallowed characters")

        # Determine the final path of the file
        resolved_file_path = self.resolve_lookup_filename(lookup_file,
                                                          namespace,
                                                          owner,
                                                          session_key=session_key,
                                                          throw_not_found=False)

        # Parse the JSON
        parsed_contents = json.loads(contents, object_pairs_hook=OrderedDict)

        # Create the temporary file
        temp_file_handle = lookupfiles.get_temporary_lookup_file()

        # This is a full path already; no need to call make_splunkhome_path().
        temp_file_name = temp_file_handle.name

        # Make the lookups directory if it does not exist
        destination_lookup_full_path = make_lookup_filename(lookup_file, namespace, owner)
        self.logger.debug("destination_lookup_full_path=%s", destination_lookup_full_path)

        destination_lookup_path_only, _ = os.path.split(destination_lookup_full_path)

        try:
            os.makedirs(destination_lookup_path_only, 0o755)
            os.chmod(destination_lookup_path_only, 0o755)
        except OSError:
            # The directory already existed, no need to create it
            self.logger.debug("Destination path of lookup already existed, no need to create it; destination_lookup_path=%s", destination_lookup_path_only)

        # Write out the new file to a temporary location
        try:
            if temp_file_handle is not None and os.path.isfile(temp_file_name):

                csv_writer = csv.writer(temp_file_handle, lineterminator='\n')

                for row in parsed_contents:

                    if not self.is_empty(row): # Prune empty rows
                        csv_writer.writerow(row)

        finally:
            if temp_file_handle is not None:
                temp_file_handle.close()

        # Determine if the lookup file exists, create it if it doesn't
        if resolved_file_path is None:
            self.logger.debug('Creating a new lookup file, user=%s, namespace=%s, lookup_file=%s, path="%s"', owner, namespace, lookup_file, temp_file_name)
            
            lookupfiles.create_lookup_table(filename=temp_file_name,
                                            lookup_file=lookup_file,
                                            namespace=namespace,
                                            owner=owner,
                                            key=session_key)

            self.logger.info('Lookup created successfully, user=%s, namespace=%s, lookup_file=%s, path="%s"', user, namespace, lookup_file, destination_lookup_full_path)

        # Edit the existing lookup otherwise
        else:

            if not is_lookup_in_users_path(resolved_file_path) or owner == 'nobody':
                lookupfiles.update_lookup_table(filename=temp_file_name,
                                                lookup_file=lookup_file,
                                                namespace=namespace,
                                                owner="nobody",
                                                key=session_key)
            else:
                lookupfiles.update_lookup_table(filename=temp_file_name,
                                                lookup_file=lookup_file,
                                                namespace=namespace,
                                                owner=owner,
                                                key=session_key)

            self.logger.info('Lookup edited successfully, user=%s, namespace=%s, lookup_file=%s',
                             user, namespace, lookup_file)

        # Tell the SHC environment to replicate the file
        try:
            self.force_lookup_replication(namespace, lookup_file, session_key)
        except ResourceNotFound:
            self.logger.info("Unable to force replication of the lookup file to other search heads; upgrade Splunk to 6.2 or later in order to support CSV file replication")
        except AuthorizationFailed:
            self.logger.warn("Unable to force replication of the lookup file (not authorized), user=%s, namespace=%s, lookup_file=%s",
                             user, namespace, lookup_file)
        except:
            self.logger.exception("Unable to force replication of the lookup file, user=%s, namespace=%s, lookup_file=%s",
                                  user, namespace, lookup_file)

        return resolved_file_path
