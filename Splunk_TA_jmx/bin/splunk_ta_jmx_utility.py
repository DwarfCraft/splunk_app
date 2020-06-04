import base64

from solnlib import conf_manager, utils, splunkenv
from splunk import admin
from splunktaucclib.rest_handler import util
from splunktaucclib.rest_handler.error import RestError

params = {
    'DESTINATION_APP_PARAM': 'destinationapp',
    'ACCOUNT_NAME_PARAM': 'account_name',
    'ACCOUNT_PASSWORD_PARAM': 'account_password',
    'CONTENT_PARAM': 'content',
    'JMX_SERVERS_CONF_FILE_NAME': 'jmx_servers',
    'JMX_TASKS_CONF_FILE_NAME': 'jmx_tasks',
    'JMX_TEMPLATES_CONF_FILE_NAME': 'jmx_templates',
    'CRED_REALM': '__REST_CREDENTIAL__#_{app_name}_account_#{destinationapp}#{stanza_name}',
    'EAI:APPNAME': 'eai:appName',
    'DISABLED_PARAM': 'disabled'
}


def is_input_exists(callerargs_id, session_key, field):
    """
    This method has checked the deletion of raw is used in tasks or not. if the value is used in task then return the tuple with True and field name
    otherwise return the tuple with False and field name.
    :param callerargs_id: parameter containing the name of the raw from the callerArgs.
    :param session_key: parameter containing the session key.
    :param field: parameter containing the field name.
    :return tuple:
    """
    app_name = util.get_base_app_name()
    field_name = app_name + ":" + callerargs_id
    cfm = conf_manager.ConfManager(session_key, app_name)
    try:
        task_objs_dict = cfm.get_conf("jmx_tasks").get_all()
        task_items = list(task_objs_dict.items())
        if task_items:
            for task, task_info in list(task_objs_dict.items()):
                fields = task_info[field]
                if field_name in fields.replace(' ', '').split('|'):
                    return True, field_name
    except:
        # Handle the case when no jmx_tasks configuration found. In this case, no need to
        # check delete raw exists in task configuration.
        pass
    return False, field_name


def check_data_duplication(servers_list, templates_list, tasks_stanza, input_name, logger):
    """
    This method validates the possibility of data duplication, warning log message and returns bool value accordingly

    :param servers_list: list of server names
    :param templates_list: list of template names
    :param tasks_stanza: dict of task stanza
    :param input_name: String containing name of input name
    :param logger: Logger object
    :return: bool
    """

    servers_list = set(servers_list)
    templates_list = set(templates_list)
    for stanza_name, content in list(tasks_stanza.items()):
        if input_name == stanza_name:
            continue
        is_disabled = content.get('disabled', '0')
        stanza_templates = set(content.get('templates', '').replace(' ', '').split('|'))
        stanza_servers = set(content.get('servers', '').replace(' ', '').split('|'))
        stanza_status = "disabled" if utils.is_true(is_disabled) else "enabled"

        # a & b returns set() containing intersection of set a and set b if there is intersection else empty set()
        if templates_list & stanza_templates and servers_list & stanza_servers:
            logger.warn(
                'Selected templates: {} and servers: {} are already present in {} stanza: {}. '
                'This may cause data duplication'.format(list(templates_list), list(servers_list), stanza_status,
                                                         stanza_name))
            return True

    return False


def update_conf_metadata(field_object, app_name):
    """
    This method has updated the appName metadata in the configuration object.
    :param field_object: configuration object.
    :param app_name: current addon name
    """
    field_object['eai:appName'] = app_name
    field_object.setMetadata(
        admin.EAI_ENTRY_ACL,
        {'app': app_name, 'owner': 'nobody'},
    )


def getConfigurationObject(session_key, destinationapp, conf_filename):
    """
    This method has checked the configuration file is exists or not. if the configuration file is available then it call ConfManager get_conf event to returns the Conf file object otherwise it calls the ConfManager create_conf event to return the Conf file object.
    :param session_key: parameter containing the session key.
    :param destinationapp: destination app/adoon name.
    :param conf_filename: configuration filename.
    :return Conf file object:
    """
    cfm = conf_manager.ConfManager(session_key, destinationapp)
    try:
        objs_dict = cfm.get_conf(conf_filename)
    except:
        objs_dict = cfm.create_conf(conf_filename)

    return objs_dict


def getNamespaceForObject(session_key, conf_filename):
    """
    This method populate destination app name if not exist in configuration
    :param session_key: parameter containing the session key.
    :param conf_filename: configuration filename.
    :return dictionary of key value pair of stanza name and destination app:
    """
    cfm = conf_manager.ConfManager(session_key, util.get_base_app_name())
    entity_namespace_mapping = dict()
    try:
        stanzas = cfm.get_conf(conf_filename).get_all()
        if stanzas:
            for stanza, stanza_info in list(stanzas.items()):
                entity_namespace_mapping[stanza] = stanza_info[params.get('EAI:APPNAME')]
    except:
        pass
    return entity_namespace_mapping


def encode(value):
    """
    Encode a string using the URL- and filesystem-safe Base64 alphabet.
    :param value: string to converted into base64
    :return: base64 encoded string
    """
    if value is None:
        return ''
    return base64.urlsafe_b64encode(value.encode('utf-8').strip())

def decode(value):
    """
    Decode a string using the URL- and filesystem-safe Base64 alphabet.
    :param value: string to be decoded
    :return: decoded string
    """
    if value is None:
        return ''
    return base64.urlsafe_b64decode(str(value))

def get_not_configure_server_list():
    """
    Fetch the server list and make a missing configured server list
    :return: not configured server list
    """
    server_list = []

    # This method is return the server configuration list.
    servers = splunkenv.get_conf_stanzas(params.get('JMX_SERVERS_CONF_FILE_NAME'))

    for key, value in list(servers.items()):
        # Check the account configuration is missing or not
        if value.get('has_account') == "1" and value.get('account_name') is None:
            server_list.append(key)
    return server_list

def _check_name_for_create(name):
    """
    Check the stanza name should not be default or not start with `_`
    :param name: stanza name
    """
    if name == 'default':
        raise RestError(
            400,
            '"%s" is not allowed for entity name' % name
        )
    if name.startswith("_"):
        raise RestError(
            400,
            'Name starting with "_" is not allowed for entity'
        )


def perform_validation(stanza_name, payload, conf_name, endpoint, existing, session_key):
    """
    perform the validation on configuration object.
    :param stanza_name: stanza name
    :param payload: payload
    :param conf_name: conf file name
    :param endpoint: endpoint object
    :param existing: boolean flag to identify create/update operation
    :param session_key: session key
    """
    if not existing:
        # Check the stanza name during create time event
        _check_name_for_create(stanza_name)

    # Check the configuration object is exist or not. set the None value if configuration object not found.
    try:
        cfm = conf_manager.ConfManager(session_key, util.get_base_app_name())
        entity = cfm.get_conf(conf_name).get(stanza_name)
        destination_app_param = params.get('DESTINATION_APP_PARAM')
        target_app = payload.get(destination_app_param)
        disabled_param = payload.get(params.get('DISABLED_PARAM'))

        # EAI Name used to update destinationapp field with addon name in which configuration is saved
        # This code block will handle the scenario in which destination field is not configured in stanza
        # destinationapp field will be populted with eai:appName value which is addon name on which conf is stored
        eai_appname = entity.get(params.get('EAI:APPNAME'))
        if target_app is None:
            if entity.get(destination_app_param) is not None:
                target_app = entity.get(destination_app_param)
            elif eai_appname is not None:
                target_app = eai_appname
            else:
                target_app = util.get_base_app_name
        elif target_app != eai_appname:
            target_app = eai_appname
        payload[destination_app_param] = target_app

        # Set the disabled key value from configuration dictionary if it's not available in the payload
        if disabled_param is None:
            payload[params.get('DISABLED_PARAM')] = entity.get(params.get('DISABLED_PARAM'))
    except:
        entity = None

    if existing and not entity:
        raise RestError(404, '"%s" does not exist' % stanza_name)
    elif not existing and entity:
        raise RestError(409, 'Name "%s" is already in use' % stanza_name)

    endpoint.validate(
        stanza_name,
        payload,
        entity,
    )
