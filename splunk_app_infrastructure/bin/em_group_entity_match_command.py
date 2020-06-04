#!/usr/bin/env python

import sys
import em_path_inject  # noqa
from splunklib.searchcommands import \
    dispatch, StreamingCommand, Configuration, Option, validators
from em_model_group import EMGroup
from em_model_entity import EmEntity
from logging_utils import log
from rest_handler.session import session

logger = log.getLogger()


@Configuration()
class EMGroupEntityMatchCommand(StreamingCommand):
    """ Match groups and entities based on group filter and entity dimensions

    ##Syntax

    .. code-block::
        emgroupentitymatch selectedGroupIds="states,aws_instances" retainInput=false

    ##Description
        This custom search command will add 'group_id' and 'group_title' to all input
        entity records if they are members of a group - otherwise it will be omitted from the results
        unless retainInput is 'true'.

        Options:
        1. selectedGroupIds -- indicates the selected groups that you want to match against the entities
        2. retainInput -- indicates if the original input records should be attached to the output records
                          if true, those records will have 'group_id' and 'group_title' set to 'N/A' for you
                          to distinguish them.

    ##Example

    .. code-block::
        | inputlookup em_entity_cache
        | emgroupentitymatch selectedGroupIds="states,aws_instances" retainInput=false
        | stats count by group_title

    """

    selected_group_ids = Option(doc='List of selected group ids, separated by comma.',
                                name='selectedGroupIds',
                                default=None,
                                require=False)
    retain_input_record = Option(doc='Boolean to indicate if user wants the input '
                                     'record to be added to the output without modification.',
                                 name='retainInput',
                                 default=False,
                                 require=False,
                                 validate=validators.Boolean())

    def stream(self, records):
        """
        Generator function that processes and yields event records to the Splunk stream pipeline.
        :param records: splunk event records
        :return:
        """
        try:
            # save authtoken into session so that subsequent routines can directly use it
            session.save(authtoken=self._metadata.searchinfo.session_key)

            for record in records:
                if self.retain_input_record:
                    record['group_id'] = 'N/A'
                    record['group_title'] = 'N/A'
                    yield record
                if len(self.groups):
                    for group in self.groups:
                        # TODO: maybe should mark _from_raw a public method?
                        entity = EmEntity._from_raw(record)
                        # check matching groups
                        if group.check_entity_membership(entity):
                            record['group_id'] = group.key
                            record['group_title'] = group.title
                            yield record
                else:
                    yield record
        finally:
            # clear session at the end so it doesn't get persisted across calls otherwise it might
            # accidentally enable unauthorized access.
            session.clear()

    @property
    def groups(self):
        '''
        A list of EMGroup objects fetched based on query, if there's no query then all groups are fetched
        '''
        if getattr(self, '_groups', None):
            return self._groups

        query = None
        if self.selected_group_ids:
            selected_group_ids = [group_id.strip()
                                  for group_id in self.selected_group_ids.split(',')]
            query = {'_key': selected_group_ids}
        self._groups = EMGroup.load(0, 0, '', 'asc', query=query)
        return self._groups


dispatch(EMGroupEntityMatchCommand, sys.argv, sys.stdin, sys.stdout, __name__)
