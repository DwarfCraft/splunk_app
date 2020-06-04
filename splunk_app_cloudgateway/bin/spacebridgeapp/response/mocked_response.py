"""
(C) 2019 Splunk Inc. All rights reserved.

Small module for mocking responses for different message types
until we have actual implementations.

Moving this to it's own module to separate the mocks from the
message processing logic
"""

from splapp_protocol import common_pb2
from spacebridgeapp.util import constants
from spacebridgeapp.util.guid_generator import get_guid

TEST_SERVER_RID = get_guid()
TEST_SUBSCRIPTION_ID = "ABCD1234"

def mock_subscribe_response(client_single_request, server_subscription_message):
    server_subscription_message.requestId = TEST_SERVER_RID
    server_subscription_message.subscriptionId = constants.TEST_SUBSCRIPTION_ID
    server_subscription_message.serverSubscribeResponse.replyToMessageId = client_single_request.requestId


def mock_unsubscribe_response(client_single_request, server_subscription_message):
    server_subscription_message.requestId = TEST_SERVER_RID
    server_subscription_message.subscriptionId = constants.TEST_SUBSCRIPTION_ID
    server_subscription_message.serverUnsubscribeResponse.replyToMessageId = client_single_request.requestId


def mock_subscription_event(server_subscription_message):
    server_subscription_message.requestId = TEST_SERVER_RID
    server_subscription_message.subscriptionId = constants.TEST_SUBSCRIPTION_ID
    server_subscription_message.serverSubscriptionEvent.dashboardVisualizationEvent.dashboardVisualizationId.dashboardId = 'dashboard_id'
    server_subscription_message.serverSubscriptionEvent.dashboardVisualizationEvent.dashboardVisualizationId.visualizationId = 'visualization_id'
    server_subscription_message.serverSubscriptionEvent.dashboardVisualizationEvent.visualizationData.fields.extend(['field'])
    server_subscription_message.serverSubscriptionEvent.dashboardVisualizationEvent.visualizationData.columns.extend([])


def mock_alerts_list_response(client_single_request, server_single_response):
    """Given a ServerSingleResponse proto, mock the alertsListResponse field
    in the ServerSingleResponse proto.

    Arguments:
        client_single_request {ClientSingleRequest Proto} - Input request from client.
        server_single_response {ServerSingleResponse Proto} - Proto encapsulating
        server response. When mocked alert is constructed, it will mutate this
        variable directly.

    """
    server_single_response.requestId = TEST_SERVER_RID
    server_single_response.replyToMessageId = client_single_request.requestId
    server_single_response.alertsListResponse.continuationId = client_single_request.alertsListRequest.continuationId
    server_single_response.alertsListResponse.nextContinuationId = "1".encode("utf8")

    alerts = []

    # Create K alerts which are identical except for the id and title
    for i in range(10):
        alerts.append(build_mock_alert("alert_" + str(i)))
    server_single_response.alertsListResponse.alerts.extend(alerts)


def mock_dashboard_list_response(client_single_request, server_single_response):
    """
    Given a server_single_response proto, mock the dashboard_list_response field in a server_single_response proto
    :param client_single_request: {ClientSingleRequest Proto} - Input request from client.
    :param server_single_response: {ServerSingleResponse Proto} - Proto encapsulating

    sever_single_response will modify object directly
    """
    server_single_response.requestId = TEST_SERVER_RID
    server_single_response.replyToMessageId = client_single_request.requestId

    dashboards = []

    for i in range(10):
        dashboards.append(build_mock_dashboard_description("dashboard_" + str(i)))
    server_single_response.dashboardListResponse.dashboards.extend(dashboards)


def mock_dashboard_get_response(client_single_request, server_single_response):
    """
        Given a server_single_response proto, mock the dashboard_get_response field in a server_single_response proto
        :param client_single_request: {ClientSingleRequest Proto} - Input request from client.
        :param server_single_response: {ServerSingleResponse Proto} - Proto encapsulating

        sever_single_response will modify object directly
        """
    server_single_response.requestId = TEST_SERVER_RID
    server_single_response.replyToMessageId = client_single_request.requestId
    server_single_response.dashboardGetResponse.dashboard = build_mock_dashboard_description("dashboard_id")


def build_mock_alert(alert_id):
    """Create a mock of the Alert proto whose id is alert_id. Fill out the
    notification and detail fields as well as some mock dashboards.
    """

    alert = common_pb2.Alert()
    alert.notification.severity = common_pb2.Alert.WARNING
    alert.notification.alertId = alert_id.encode("utf8")
    alert.notification.title = "Title for " + alert_id
    alert.notification.description = "Something bad happened"
    alert.notification.callToAction.uri = "https://fakeserver.com:4080/reboot_everything"
    alert.notification.callToAction.title = "Reboot servers"
    alert.notification.createdAt = "1527102201"
    alert.detail.resultJson = "{}"
    alert.detail.searchId = "test_search_id"
    alert.detail.resultsLink = "www.fake_link.com"
    alert.detail.searchName = "test search"
    alert.detail.owner = "mobile-prime"
    alert.detail.dashboardId = "test_dashboard_id"
    alert.detail.dashboardDefinition.dashboardId = "test_dashboard_id"
    alert.detail.dashboardDefinition.title = "Test Dashboard Title"
    alert.detail.dashboardDefinition.description = "Test Dashboard Description"
    alert.detail.dashboardDefinition.rows.extend([build_mock_row(), build_mock_row()])

    return alert


def build_mock_row():
    """Create a mock Dashboard Row
    """

    row = common_pb2.DashboardRow()
    row.panels.extend([build_mock_panel("panel 1"), build_mock_panel("panel 2")])
    return row


def build_mock_panel(title):
    """Create a mock Dashboard Panel
    """

    panel = common_pb2.DashboardPanel()
    panel.title = title
    panel.visualizations.extend([build_mock_chart("test_search_id_1"), build_mock_chart("test_search_id_2")])

    return panel


def build_mock_chart(search_id):
    """Create a mock Dashboard Chart
    """

    chart = common_pb2.DashboardVisualization()
    chart.type = common_pb2.DashboardVisualization.DASHBOARD_VISUALIZATION_CHART
    chart.id = search_id
    chart.search.earliest = "test_earliest"
    chart.search.latest = "test_latest"
    chart.search.refresh = "test_refresh"
    chart.search.refreshType = 0
    chart.search.sampleRatio = 0.1
    chart.search.postSearch = "test_post_search"
    chart.options["test_option"] = "test_option_value"
    return chart


def build_mock_dashboard_description(dashboard_id):
    """
    Create mock DashboardDescription
    """

    description = common_pb2.DashboardDescription()
    description.dashboardId = dashboard_id
    description.title = "Title for " + dashboard_id
    description.description = "Description for " + dashboard_id
    description.appName = "app_name"
    description.usesCustomCss = False
    description.usesCustomJavascript = False
    description.usesCustomVisualization = False
    description.usesCustomHtml = False
    description.isFavorite = True
    description.definition.dashboardId = dashboard_id
    description.definition.title = description.title
    description.definition.description = description.description
    description.definition.rows.extend([build_mock_row(), build_mock_row()])
    return description
