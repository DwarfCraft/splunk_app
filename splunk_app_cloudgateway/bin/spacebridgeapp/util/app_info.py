"""
(C) 2019 Splunk Inc. All rights reserved.

Helpers to get related app info entry objects given an app_name or objects from which we
can parse out an app_name
"""

from spacebridgeapp.logging import setup_logging
from spacebridgeapp.util import constants
from spacebridgeapp.util.constants import ALERTS_IOS, APPLE_TV, AR_PLUS, VR, NLP, IOS, ANDROID, DRONE_MODE
from twisted.internet import defer
from twisted.web import http

LOGGER = setup_logging(constants.SPACEBRIDGE_APP_NAME + '_dashboard_app_info.log', 'dashboard_app_info')

DISPLAY_APP_NAMES = {}


@defer.inlineCallbacks
def fetch_display_app_name(request_context, app_name, async_splunk_client):
    """
        Use the client to fetch the display app name. If all the entry response objects don't match the
        target app_name, this function will return the provided app_name.

    :param request_context:
    :param app_name: The app name to use for display_app_name lookup
    :param async_splunk_client: The client to use for getting the app info entries
    :return:
    """

    if app_name in DISPLAY_APP_NAMES:
        defer.returnValue(DISPLAY_APP_NAMES[app_name])

    try:
        app_info_response = yield async_splunk_client.async_get_app_info(app_name=app_name,
                                                                         auth_header=request_context.auth_header)

        if app_info_response.code != http.OK:
            error = yield app_info_response.text()
            LOGGER.warning("Fetch for app info failed. status_code={}, error={}".format(app_info_response.code, error))
            defer.returnValue(app_name)

        app_info_json = yield app_info_response.json()
        info_entry = app_info_json['entry'][0]
        display_app_name = info_entry['content']['label']
        DISPLAY_APP_NAMES[app_name] = display_app_name
        LOGGER.info("Fetched Display App Name: app_name={}, display_app_name={}".format(app_name, display_app_name))
        defer.returnValue(display_app_name)
    except Exception:
        LOGGER.exception("Unable to fetch display app name for app_name=%s", app_name)

    # If all else fails just return app_name
    defer.returnValue(app_name)


def resolve_app_name(app_id):
    """
    Function maps app id to app category
    :param app_id:
    :return:
    """
    app_id_map = {
        "com.splunk.mobile.Stargate": ALERTS_IOS,
        "com.splunk.mobile.Alerts": ALERTS_IOS,
        "com.splunk.android.alerts": ALERTS_IOS,
        "com.splunk.android.alerts.debug": ALERTS_IOS,
        "com.splunk.mobile.Ribs": ALERTS_IOS,
        "com.splunk.DashKit.Example": ALERTS_IOS,
        "com.splunk.mobile.SplunkTV": APPLE_TV,
        "com.splunk.mobile.SplunkTvOS": APPLE_TV,
        "com.splunk.mobile.ARDemo": AR_PLUS,
        "com.splunk.mobile.SplunkAR": AR_PLUS,
        "com.splunk.mobile.vrtest": AR_PLUS,
        "com.splunk.mobile.vr": AR_PLUS,
        "com.splunk.nlp.cloud": NLP,
        "com.splunk.mobile.DroneTV": DRONE_MODE,
        "com.splunk.mobile.DroneController": DRONE_MODE,
    }
    return app_id_map.get(app_id)


def get_app_platform(app_id):
    """
    Function maps app id to app platform
    :param app_id:
    :return:
    """
    app_id_map = {
        "com.splunk.mobile.Stargate": IOS,
        "com.splunk.mobile.Alerts": IOS,
        "com.splunk.mobile.Ribs": IOS,
        "com.splunk.DashKit.Example": IOS,
        "com.splunk.android.alerts": ANDROID,
        "com.splunk.android.alerts.debug": ANDROID,
        "com.splunk.mobile.SplunkTV": APPLE_TV,
        "com.splunk.mobile.SplunkTvOS": APPLE_TV,
        "com.splunk.mobile.ARDemo": IOS,
        "com.splunk.mobile.SplunkAR": IOS,
        "com.splunk.mobile.vrtest": VR,
        "com.splunk.mobile.vr": VR,
        "com.splunk.nlp.cloud": NLP,
        "com.splunk.mobile.DroneTV": IOS,
        "com.splunk.mobile.DroneController": IOS,
        "com.splunk.mobile.Ribs": IOS,
    }
    return app_id_map.get(app_id)
