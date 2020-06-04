import import_declare_test

from splunktaucclib.rest_handler.endpoint import (
    field,
    validator,
    RestModel,
    SingleModel,
)
from splunktaucclib.rest_handler import admin_external, util
from splunktaucclib.rest_handler.admin_external import AdminExternalHandler
from splunk_ta_jmx_rh_server_field_validation import RequiredFieldValidation
import logging
from solnlib import conf_manager, credentials
import splunk_ta_jmx_utility as common_utility
from splunk import admin

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
            min_len=1,
        )
    ),
    field.RestField(
        'protocol',
        required=True,
        encrypted=False,
        default=None,
        validator=RequiredFieldValidation()
    ),
    field.RestField(
        'stubSource',
        required=False,
        encrypted=False,
        default=None,
        validator=None
    ),
    field.RestField(
        'encodedStub',
        required=False,
        encrypted=False,
        default=None,
        validator=validator.String(
            max_len=255,
            min_len=1,
        )
    ),
    field.RestField(
        'host',
        required=False,
        encrypted=False,
        default=None,
        validator=None
    ),
    field.RestField(
        'jmxport',
        required=False,
        encrypted=False,
        default=None,
        validator=validator.AllOf(
            validator.Pattern(
                regex=r"""^\d+$""",
            ),
            validator.Pattern(
                regex=r"""^([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$""",
            )
        )
    ),
    field.RestField(
        'lookupPath',
        required=False,
        encrypted=False,
        default=None,
        validator=None
    ),
    field.RestField(
        'pidCommand',
        required=False,
        encrypted=False,
        default=None,
        validator=None
    ),
    field.RestField(
        'pid',
        required=False,
        encrypted=False,
        default=None,
        validator=validator.AllOf(
            validator.Pattern(
                regex=r"""^\d+$""",
            ),
            validator.Pattern(
                regex=r"""^([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$""",
            )
        )
    ),
    field.RestField(
        'pidFile',
        required=False,
        encrypted=False,
        default=None,
        validator=None
    ),
    field.RestField(
        'jmx_url',
        required=False,
        encrypted=False,
        default=None,
        validator=validator.Pattern(
            regex=r"""^service:jmx.*$""",
        )
    ),
    field.RestField(
        'account_name',
        required=False,
        encrypted=False,
        default=None,
        validator=validator.String(
            max_len=255,
            min_len=1,
        )
    ),
    field.RestField(
        'account_password',
        required=False,
        encrypted=True,
        default=None,
        validator=validator.String(
            max_len=255,
            min_len=1,
        )
    ),
    field.RestField(
        'interval',
        required=False,
        encrypted=False,
        default=None,
        validator=validator.Number(
            max_val=31536000,
            min_val=1,
        )
    ),

    field.RestField(
        'disabled',
        required=False,
        validator=None
    )

]
model = RestModel(fields, name=None)

endpoint = SingleModel(
    'jmx_servers',
    model,
    config_name='server'
)


class JMXServerHandler(AdminExternalHandler):
    """
    This class handles the parameters in the configuration page
    """

    def __init__(self, *args, **kwargs):
        AdminExternalHandler.__init__(self, *args, **kwargs)

    def handleList(self, conf_info):
        """
        This method is called when server is rendered with configurable parameters from jmx_servers.conf
        :param conf_info: The dictionary used to display configurable parameters.
        :return: None
        """
        app_name = util.get_base_app_name()
        AdminExternalHandler.handleList(self, conf_info)
        mapping = common_utility.getNamespaceForObject(self.getSessionKey(),
                                                       common_utility.params.get('JMX_SERVERS_CONF_FILE_NAME'))
        # Update the configuration object list metadata with the current app name.
        for name, value in list(conf_info.items()):
            if value.get(common_utility.params.get('DESTINATION_APP_PARAM')) is None and name in mapping:
                value[common_utility.params.get('DESTINATION_APP_PARAM')] = mapping.get(name)

            if value.get('eai:appName'):
                common_utility.update_conf_metadata(value, app_name)

    def handle_request(self, conf_info, is_handle_edit_operation):
        """
        This method is called when new server configuration is created/updated.
        :param conf_info: The dictionary containing configurable parameters.
        :param is_handle_edit_operation: Boolean flag to check the configuration object is in create/update mode.
        :return: None
        """

        # Perform the server form field validation
        common_utility.perform_validation(self.callerArgs.id, self.payload, common_utility.params.get('JMX_SERVERS_CONF_FILE_NAME'), endpoint,
        is_handle_edit_operation, self.getSessionKey())

        app_name = util.get_base_app_name()
        destinationapp = self.payload.get(common_utility.params.get('DESTINATION_APP_PARAM'))
        account_name = self.payload.get(common_utility.params.get('ACCOUNT_NAME_PARAM'))
        account_password = self.payload.get(common_utility.params.get('ACCOUNT_PASSWORD_PARAM'))
        session_key = self.getSessionKey()
        stanza_name = self.callerArgs.id

        # Using the ConfManager get conf file object.
        conf_obj = common_utility.getConfigurationObject(session_key, destinationapp, common_utility.params.get('JMX_SERVERS_CONF_FILE_NAME'))

        # we can save the password in a separate password.conf file. hence remove the password in the payload and set balnk value in conf_info object.
        if account_password:
            del self.payload[common_utility.params.get('ACCOUNT_PASSWORD_PARAM')]
            conf_info[stanza_name][common_utility.params.get('ACCOUNT_PASSWORD_PARAM')] = ''
        conf_obj.update(stanza_name, self.payload)

        # create/update the password in JMX addon password.conf file.
        if account_password and account_name:
            realm = common_utility.params.get('CRED_REALM').format(app_name=app_name, destinationapp=destinationapp, stanza_name=stanza_name)
            crm = credentials.CredentialManager(session_key, app_name, realm=realm)
            crm.set_password(account_name, account_password)

        # Update the configuration object metadata with the current app name.
        common_utility.update_conf_metadata(conf_info[stanza_name], app_name)

    def handleCreate(self, conf_info):
        """
        This method is called when new server configuration is created.
        :param conf_info: The dictionary containing configurable parameters.
        :return: None
        """
        self.handle_request(conf_info, False)

    def handleEdit(self, conf_info):
        """
        This method is called when server configuration is updated.
        :param conf_info: The dictionary containing configurable parameters.
        :return: None
        """
        self.handle_request(conf_info, True)

    # Override the delete server method to prevent deletion of server which is in use
    def handleRemove(self, conf_info):
        """
        This method is called when server is deleted. It deletes the server raw if it's not used in task configuration.
        :param conf_info: The dictionary containing configurable parameters.
        :return: None
        """
        session_key = self.getSessionKey()
        app_name = util.get_base_app_name()
        stanza_name = self.callerArgs.id

        # Using the ConfManager get conf file object.
        conf_obj = common_utility.getConfigurationObject(session_key, app_name, common_utility.params.get('JMX_SERVERS_CONF_FILE_NAME'))
        conf_data = conf_obj.get(stanza_name)

        account_name = conf_data.get(common_utility.params.get('ACCOUNT_NAME_PARAM'))
        destinationapp = conf_data.get(common_utility.params.get('DESTINATION_APP_PARAM'))

        is_input_exist, field_name = common_utility.is_input_exists(stanza_name, session_key, "servers")
        if is_input_exist:
            raise Exception("\"{}\" cannot be deleted because it is used in inputs".format(field_name))
        # If server is not in use, continue to remove the server by calling conf manager delete method.
        conf_obj.delete(stanza_name)

        # Removed credential configuration from JMX addon password.conf file.
        if account_name:
            realm = common_utility.params.get('CRED_REALM').format(app_name=app_name, destinationapp=destinationapp, stanza_name=stanza_name)
            crm = credentials.CredentialManager(session_key, app_name, realm=realm)
            crm.delete_password(account_name)


if __name__ == '__main__':
    logging.getLogger().addHandler(logging.NullHandler())
    admin_external.handle(
        endpoint,
        handler=JMXServerHandler,
    )
