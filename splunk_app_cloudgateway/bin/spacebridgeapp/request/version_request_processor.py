from twisted.internet import defer
from twisted.web import http

from spacebridgeapp.data.telemetry_data import InstallationEnvironment
from spacebridgeapp.util import constants
from spacebridgeapp.logging import setup_logging
from spacebridgeapp.versioning import app_version, minimum_build
from splapp_protocol import request_pb2

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + "_version_request_processor", "version_request_processor")


@defer.inlineCallbacks
def process_get_version_request(request_context,
                                client_single_request,
                                server_single_response,
                                async_client_factory):
    """
    Process getVersionRequest by returning splunk app version number, min supported client version and friendly name
    for device
    :param request_context:
    :param client_single_request:
    :param server_single_response:
    :param async_client_factory:
    :return:
    """
    LOGGER.debug("Processing get version")

    async_kvstore_client = async_client_factory.kvstore_client()
    async_telemetry_client = async_client_factory.telemetry_client()

    try:
        server_single_response.versionGetResponse.SetInParent()
        server_single_response.versionGetResponse.cloudgatewayAppVersion = str(app_version())

        user_agent = request_context.user_agent or "invalid"
        agent_parts = user_agent.split('|')
        app_id = agent_parts[0]

        app_min_build = minimum_build(app_id)
        server_single_response.versionGetResponse.minimumClientVersion = str(app_min_build)

        auth_header = request_context.auth_header
        device_name = yield _get_device_name(auth_header, auth_header.username, request_context.device_id,
                                             async_kvstore_client, request_context)

        server_single_response.versionGetResponse.deviceName = device_name

        deployment_friendly_name = yield _get_deployment_friendly_name(auth_header, async_kvstore_client, request_context)
        server_single_response.versionGetResponse.deploymentFriendlyName = deployment_friendly_name

        telemetry_instance_id = yield async_telemetry_client.get_telemetry_instance_id(auth_header)
        server_single_response.versionGetResponse.instanceId = telemetry_instance_id

        installation_environment = yield async_telemetry_client.get_installation_environment(auth_header)
        installation_environment_proto = request_pb2.VersionGetResponse.CLOUD \
            if installation_environment is InstallationEnvironment.CLOUD \
            else request_pb2.VersionGetResponse.ENTERPRISE
        server_single_response.versionGetResponse.installationEnvironment = installation_environment_proto

        splunk_version = yield async_telemetry_client.get_splunk_version(auth_header)
        server_single_response.versionGetResponse.splunkVersion = splunk_version
    except Exception:
        LOGGER.exception("Exception getting version info")

    LOGGER.debug("Finished processing get version")


@defer.inlineCallbacks
def _get_device_name(auth_header, user, device_id, async_kvstore_client, request_context):
    """
    Get friendly name for device given it's device id
    :param auth_header:
    :param user:
    :param device_id:
    :param async_kvstore_client:
    :return:
    """

    response = yield async_kvstore_client.async_kvstore_get_request(
        constants.REGISTERED_DEVICES_COLLECTION_NAME, auth_header=auth_header, owner=user)

    if response.code == http.OK:
        response_json = yield response.json()

        for device in response_json:
            if device["device_id"] == device_id:
                defer.returnValue(device["device_name"])

    LOGGER.error("Unable to fetch friendly name for device={}, code={}".format(device_id, response.code))
    defer.returnValue("")

@defer.inlineCallbacks
def _get_deployment_friendly_name(auth_header, async_kvstore_client, request_context):
    """
    Get friendly name for deployment
    :param auth_header:
    :param async_kvstore_client:
    :return:
    """

    response = yield async_kvstore_client.async_kvstore_get_request(
        constants.META_COLLECTION_NAME, auth_header=auth_header, owner=constants.NOBODY)

    if response.code == http.OK:
        response_json = yield response.json()
        defer.returnValue(response_json[0][constants.DEPLOYMENT_FRIENDLY_NAME])

    LOGGER.error("Unable to fetch deployment friendly name for instance, code={}".format(response.code))
    defer.returnValue("")

