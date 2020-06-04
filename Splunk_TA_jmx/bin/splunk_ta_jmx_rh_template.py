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

fields = [
    field.RestField(
        'destinationapp',
        required=True,
        encrypted=False,
        default='Splunk_TA_jmx',
        validator=validator.String(
            max_len=255,
            min_len=1,
        )
    ),
    field.RestField(
        'description',
        required=False,
        encrypted=False,
        default=None,
        validator=validator.String(
            max_len=500,
            min_len=0,
        )
    ),
    field.RestField(
        'content',
        required=True,
        encrypted=False,
        default=None,
        validator=None
    )
]
model = RestModel(fields, name=None)

endpoint = SingleModel(
    'jmx_templates',
    model,
    config_name='template'
)


class JMXTemplateHandler(AdminExternalHandler):
    """
    This class handles the parameters in the configuration page
    """

    def __init__(self, *args, **kwargs):
        AdminExternalHandler.__init__(self, *args, **kwargs)

    def handleList(self, conf_info):
        """
        This method is called when template is rendered with configurable parameters from jmx_templates.conf
        after decoding base64 value of content field

        :param conf_info: The dictionary used to display configurable parameters.
        :return: None
        """
        app_name = util.get_base_app_name()
        AdminExternalHandler.handleList(self, conf_info)
        mapping = common_utility.getNamespaceForObject(self.getSessionKey(),
                                                       common_utility.params.get('JMX_TEMPLATES_CONF_FILE_NAME'))
        for name, value in list(conf_info.items()):
            if value.get(common_utility.params.get('DESTINATION_APP_PARAM')) is None and name in mapping:
                value[common_utility.params.get('DESTINATION_APP_PARAM')] = mapping.get(name)
            if value.get('eai:appName'):
                common_utility.update_conf_metadata(value, app_name)
            if value.get('content'):
                value['content'] = common_utility.decode(value['content'])

    def handle_request(self, conf_info, is_handle_edit_operation):

        # Perform the template form field validation
        common_utility.perform_validation(self.callerArgs.id, self.payload, common_utility.params.get('JMX_TEMPLATES_CONF_FILE_NAME'), endpoint,
        is_handle_edit_operation, self.getSessionKey())

        app_name = util.get_base_app_name()
        session_key = self.getSessionKey()
        stanza_name = self.callerArgs.id
        destinationapp = self.payload.get(common_utility.params.get('DESTINATION_APP_PARAM'))

        # Using the ConfManager get conf file object.
        conf_obj = common_utility.getConfigurationObject(session_key, destinationapp, common_utility.params.get('JMX_TEMPLATES_CONF_FILE_NAME'))

        content = self.payload[common_utility.params.get('CONTENT_PARAM')]
        # Encode the content field value before storing in the configuration file.
        self.payload[common_utility.params.get('CONTENT_PARAM')] = common_utility.encode(content)
        conf_obj.update(stanza_name, self.payload)
        # Set the original content field value in conf_info after storing in the conf file.
        conf_info[stanza_name][common_utility.params.get('CONTENT_PARAM')] = content
        common_utility.update_conf_metadata(conf_info[stanza_name], app_name)

    def handleCreate(self, conf_info):
        """
        This method is called when new template is created. It stores values of configurable parameters after
        encoding value of content field in base64 string
        :param conf_info: The dictionary containing configurable parameters.
        :return: None
        """
        self.handle_request(conf_info, False)

    def handleEdit(self, conf_info):
        """
        This method is called when template is updated. It updates values of configurable paramters after
        encoding value of content field in base64 string
        :param conf_info: The dictionary containing configurable parameters.
        :return: None
        """
        self.handle_request(conf_info, True)


    def handleRemove(self, confInfo):
        """
        This method is called when template is deleted. It deletes the template raw if it's not used in task configuration.
        :param conf_info: The dictionary containing configurable parameters.
        :return: None
        """
        is_input_exist, field_name = common_utility.is_input_exists(self.callerArgs.id, self.getSessionKey(), "templates")
        if is_input_exist:
            raise Exception('"{}" cannot be deleted because it is used in inputs'.format(field_name))
        # If template is not in use, continue to remove the template by calling super method
        AdminExternalHandler.handleRemove(self, confInfo)


if __name__ == '__main__':
    logging.getLogger().addHandler(logging.NullHandler())
    admin_external.handle(
        endpoint,
        handler=JMXTemplateHandler,
    )
