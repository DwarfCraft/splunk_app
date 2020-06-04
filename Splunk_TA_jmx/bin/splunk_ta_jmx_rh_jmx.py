
import import_declare_test

from splunktaucclib.rest_handler.endpoint import (
    field,
    validator,
    RestModel,
    SingleModel,
)
from splunktaucclib.rest_handler import admin_external, util
from splunktaucclib.rest_handler.admin_external import AdminExternalHandler
from solnlib import conf_manager
from splunk import admin
import logging
import splunk_ta_jmx_utility as common_utility

util.remove_http_proxy_env_vars()
APPNAME = util.get_base_app_name()


fields = [
    field.RestField(
        'destinationapp',
        required=True,
        encrypted=False,
        default='Splunk_TA_jmx',
        validator=None
    ),
    field.RestField(
        'description',
        required=False,
        encrypted=False,
        default=None,
        validator=None
    ),
    field.RestField(
        'interval',
        required=True,
        encrypted=False,
        default=60,
        validator=validator.Number(
            max_val=31536000,
            min_val=1,
        )
    ),
    field.RestField(
        'sourcetype',
        required=True,
        encrypted=False,
        default='jmx',
        validator=None
    ),
    field.RestField(
        'index',
        required=True,
        encrypted=False,
        default='default',
        validator=validator.String(
            max_len=80,
            min_len=1,
        )
    ),
    field.RestField(
        'servers',
        required=False,
        encrypted=False,
        default=None,
        validator=None
    ),
    field.RestField(
        'templates',
        required=False,
        encrypted=False,
        default=None,
        validator=None
    ),

    field.RestField(
        'disabled',
        required=False,
        validator=None
    )

]
model = RestModel(fields, name=None)


endpoint = SingleModel(
    'jmx_tasks',
    model,
    config_name='jmx'
)

class JMXInputHandler(AdminExternalHandler):
    """
    This class handles the parameters in the input page
    """

    def __init__(self, *args, **kwargs):
        AdminExternalHandler.__init__(self, *args, **kwargs)

    def handleList(self, conf_info):
        """
        This method is called when task is rendered with configurable parameters from jmx_tasks.conf
        :param conf_info: The dictionary used to display configurable parameters.
        :return: None
        """
        app_name = util.get_base_app_name()
        AdminExternalHandler.handleList(self, conf_info)

        # Update the configuration object list metadata with the current app name.
        # Set the not_configure_servers key in configuration object to pass the input connect missing server string.
        server_list = common_utility.get_not_configure_server_list()
        mapping = common_utility.getNamespaceForObject(self.getSessionKey(),
                                                       common_utility.params.get('JMX_TASKS_CONF_FILE_NAME'))
        for name, value in list(conf_info.items()):
            if value.get(common_utility.params.get('DESTINATION_APP_PARAM')) is None and name in mapping:
                value[common_utility.params.get('DESTINATION_APP_PARAM')] = mapping.get(name)

            not_configure_servers = []
            if value.get('eai:appName'):
                common_utility.update_conf_metadata(value, APPNAME)

            # Set the not_configure_servers value blank if input not connect with any missing servers else set the comma separator missing servers.
            if value.get('servers'):
                server_names = value.get('servers').replace(' ', '').split('|')
                for server_name in server_names:
                    server_name = server_name.split(":")[1]
                    if server_name in server_list:
                        not_configure_servers.append(server_name)
            value['not_configure_servers'] = '", '.join(not_configure_servers) if not_configure_servers else ""

    def handle_request(self, conf_info, is_handle_edit_operation):
        """
        This method is called when new input configuration is created/updated.
        :param conf_info: The dictionary containing configurable parameters.
        :param is_handle_edit_operation: Boolean flag to check the configuration object is in create/update mode.
        :return: None
        """

        # Perform the input form field validation
        common_utility.perform_validation(self.callerArgs.id, self.payload, common_utility.params.get('JMX_TASKS_CONF_FILE_NAME'), endpoint, is_handle_edit_operation, self.getSessionKey())

        app_name = util.get_base_app_name()
        session_key = self.getSessionKey()
        stanza_name = self.callerArgs.id
        destinationapp = self.payload.get(common_utility.params.get('DESTINATION_APP_PARAM'))

        # Using the ConfManager get conf file object.
        conf_obj = common_utility.getConfigurationObject(session_key, destinationapp, common_utility.params.get('JMX_TASKS_CONF_FILE_NAME'))
        conf_obj.update(stanza_name, self.payload)

        # Update the configuration object metadata with the current app name.
        common_utility.update_conf_metadata(conf_info[stanza_name], app_name)
        conf_info[stanza_name][common_utility.params.get('DISABLED_PARAM')] = self.payload.get(common_utility.params.get('DISABLED_PARAM'))

    def handleCreate(self, conf_info):
        """
        This method is called when new input configuration is created.
        :param conf_info: The dictionary containing configurable parameters.
        :return: None
        """
        self.handle_request(conf_info, False)

    def handleEdit(self, conf_info):
        """
        This method is called when input configuration is updated.
        :param conf_info: The dictionary containing configurable parameters.
        :return: None
        """
        self.handle_request(conf_info, True)

if __name__ == '__main__':
    logging.getLogger().addHandler(logging.NullHandler())
    admin_external.handle(
        endpoint,
        handler=JMXInputHandler,
    )
