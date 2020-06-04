"""
(C) 2019 Splunk Inc. All rights reserved.

Module to process Group Requests
"""

import json
from twisted.internet import defer
from twisted.web import http
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.exceptions.spacebridge_exceptions import SpacebridgeApiRequestError
from spacebridgeapp.tv.data.group_data import Group
from spacebridgeapp.tv.data.resource_type import ResourceType
from spacebridgeapp.util import constants


LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_group_request_processor.log", "group_request_processor")


@defer.inlineCallbacks
def process_group_get_request(request_context, client_single_request, server_single_response, async_kvstore_client):
    """
    This method processes group get requests

    :param request_context:
    :param client_single_request:
    :param server_single_response:
    :param async_kvstore_client:
    :return:
    """

    # request params
    group_id = client_single_request.groupGetRequest.groupId
    resource_type = ResourceType.from_value(client_single_request.groupGetRequest.resourceType)

    if resource_type:
        query = {constants.RESOURCE_TYPE: str(resource_type.value)}
        params = {constants.QUERY: json.dumps(query)}
    else:
        params = None

    # if group_id is specified return the specific group_id otherwise return all groups of particular resource_type
    if group_id:
        groups = yield fetch_groups(request_context, async_kvstore_client, params, key_id=group_id)
    elif resource_type != ResourceType.INVALID:
        groups = yield fetch_groups(request_context, async_kvstore_client, params)
    else:
        raise SpacebridgeApiRequestError("Unable to get group Invalid ResourceType resource_type={}"
                                         .format(resource_type))

    # groups to protos
    group_protos = [group.to_protobuf() for group in groups]

    # populate get response
    del server_single_response.groupGetResponse.groups[:]
    server_single_response.groupGetResponse.groups.extend(group_protos)
    LOGGER.debug("Call to GROUPS GET succeeded, groupId={}, resource_type={}".format(group_id, resource_type))


@defer.inlineCallbacks
def fetch_groups(request_context, async_kvstore_client, params, key_id=None):
    """
    Function to fetch groups of the resource type specified in params
    @param request_context:
    @param async_kvstore_client:
    @param params:
    @param key_id:
    """
    responses = []

    for owner in [request_context.current_user, constants.NOBODY]:
        response = async_kvstore_client.async_kvstore_get_request(
            collection=constants.GROUPS_COLLECTION_NAME,
            owner=owner,
            params=params,
            key_id=key_id,
            auth_header=request_context.auth_header)
        responses.append(response)
    result = yield defer.DeferredList(responses)
    success = all(element[0] for element in result)
    if not success:
        error = SpacebridgeApiRequestError(
            "Unable to get groups. At least one group fetch request failed to complete")
        raise error
    (user_response, global_response) = [element[1] for element in result]

    if user_response.code != http.OK and global_response.code != http.OK:
        global_error = yield global_response.text()
        user_error = yield user_response.text()
        error = yield SpacebridgeApiRequestError(
            "Unable to get groups. user_groups status code={}, global_groups status code={}"
            " user_error={}, global_error={}"
            .format(user_response.code,
                    global_response.code,
                    user_error,
                    global_error))
        raise error

    groups = []
    for response in (user_response, global_response):
        if response.code == http.OK:
            response_json = yield response.json()
            if response_json:
                if key_id is None:
                    groups.extend([Group.from_json(group) for group in response_json])
                else:
                    groups.append(Group.from_json(response_json))

    defer.returnValue(groups)


@defer.inlineCallbacks
def process_group_set_request(request_context, client_single_request, server_single_response, async_kvstore_client):
    """
    This method processes group set requests

    :param request_context:
    :param client_single_request:
    :param server_single_response:
    :param async_kvstore_client:
    :return:
    """
    # request params
    group = Group.from_proto(client_single_request.groupSetRequest.group)
    is_public = client_single_request.groupSetRequest.isPublic

    # validate Group object, must have resource type, resource_ids and name specified
    if not group or not group.is_valid():
        raise SpacebridgeApiRequestError("Unable to set group.  Invalid input {}"
                                         .format(group if group else "group=None"))

    group.resource_type = str(group.resource_type)

    # post new group
    if is_public:
        response = yield async_kvstore_client.async_kvstore_post_request(
            collection=constants.GROUPS_COLLECTION_NAME,
            owner=constants.NOBODY,
            data=group.to_json(),
            key_id=group.key(),
            auth_header=request_context.auth_header)

    else:
        response = yield async_kvstore_client.async_kvstore_post_request(
            collection=constants.GROUPS_COLLECTION_NAME,
            owner=request_context.current_user,
            data=group.to_json(),
            key_id=group.key(),
            auth_header=request_context.auth_header)

    if response.code in [http.OK, http.CREATED]:
        response_json = yield response.json()
        group_id = response_json.get(constants.KEY)
        group._key = group_id
        LOGGER.debug("Group Created. group_id={}".format(group_id))

    # Group already exists so update existing key
    elif response.code == http.CONFLICT:
        # in this case the mapping already exists, so make an update post request
        response = yield async_kvstore_client.async_kvstore_post_request(collection=constants.GROUPS_COLLECTION_NAME,
                                                                         owner=request_context.current_user,
                                                                         data=group.to_json(),
                                                                         auth_header=request_context.auth_header,
                                                                         key_id=group.key())

        if response.code != http.OK:
            raise SpacebridgeApiRequestError("Unable to set group. Invalid input {}"
                                             .format(group if group else "group=None"))
        else:
            response_json = yield response.json()
            group_id = response_json.get(constants.KEY)
            group._key = group_id
            LOGGER.debug("Group Updated. group_id={}".format(group_id))
    else:
        error = yield response.text()
        raise SpacebridgeApiRequestError(
            "Unable to set group. status_code={}, error={}, {}".format(response.code, error, group))

    server_single_response.groupSetResponse.groupId = group.key()
    LOGGER.debug("Call to GROUPS SET succeeded, groupId={}".format(group.key()))


@defer.inlineCallbacks
def process_group_delete_request(request_context, client_single_request, server_single_response, async_kvstore_client):
    """
    This method processes and group delete requests

    :param request_context:
    :param client_single_request:
    :param server_single_response:
    :param async_kvstore_client:
    :return:
    """
    # request params
    group_ids = client_single_request.groupDeleteRequest.groupIds
    is_public = client_single_request.groupDeleteRequest.isPublic

    owner = constants.NOBODY if is_public else request_context.current_user

    query = {constants.OR_OPERATOR: [{constants.KEY: group_id} for group_id in group_ids]}

    response = yield async_kvstore_client.async_kvstore_delete_request(collection=constants.GROUPS_COLLECTION_NAME,
                                                                       owner=owner,
                                                                       auth_header=request_context.auth_header,
                                                                       params={constants.QUERY: json.dumps(query)})
    if response.code != http.OK:
        message = yield response.text()
        raise SpacebridgeApiRequestError("Call to GROUPS DELETE failed with groupIds={}, code={}, message={}"
                                         .format(group_ids, response.code, message))

    # populate delete response
    server_single_response.groupDeleteResponse.SetInParent()
    LOGGER.debug("Call to GROUPS DELETE succeeded, groupIds={}".format(group_ids))
