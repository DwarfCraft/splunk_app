from __future__ import print_function
import sys
from builtins import str
import import_declare_test
import base64
import os
import xml.etree.ElementTree as ET
import java_const

from solnlib import conf_manager
from solnlib import log
from solnlib import splunkenv
from splunktaucclib.rest_handler import util

from splunk_ta_jmx_utility import check_data_duplication, decode

log.Logs.set_context()
APPNAME = util.get_base_app_name()
LOGGER = log.Logs().get_logger('ta_jmx_task_monitor')
FIELDS_TO_DELETE = ['description', 'jmx_url', 'account_name', 'account_password', 'eai:userName', 'eai:access',
                    'eai:appName', 'destinationapp', 'disabled']
JMX_INPUT_PREFIX = "jmx://_{}_:".format(APPNAME)



def get_stanza_configuration(config_manager_obj, conf_file_name):
    """
    This method returns dict of stanzas for conf_file_name file using given config_manager_obj

    :param config_manager_obj: Object of conf manager
    :param conf_file_name: String containing file name
    :return: dict
    """
    try:
        # Get configurations from all apps
        configuration = config_manager_obj.get_conf(conf_file_name).get_all(only_current_app=False)
        return configuration
    except:
        # return empty dict when no configuration found
        return {}


def delete_server_fields_for_xml(server_dict):
    """
    This methods removes the fields not required in XML

    :param server_dict: dict of server configurations
    :return: None
    """
    if (server_dict.get('jmxServiceURL') or server_dict.get('pid') or server_dict.get('pidFile')) and 'protocol' in server_dict:
        del server_dict['protocol']

    for field in FIELDS_TO_DELETE:
        if field in server_dict:
            del server_dict[field]


def get_server_dict_to_xml(server_dict, server_name):
    """
    This method creates XML for server configuration using server_dict and server_name

    :param server_dict: dict of server configuration
    :param server_name: string containing server name
    :return: string
    """

    def confidential_name():
        prefix = "_{}_account_".format(APPNAME)
        return '{}#{}#{}'.format(prefix, server_dict.get('destinationapp'), server_name)

    if server_dict.get('description'):
        server_dict['jvmDescription'] = server_dict['description']

    if server_dict.get('jmx_url'):
        server_dict['jmxServiceURL'] = server_dict['jmx_url']

    # To handle the scenario of upgrade as this field is not present in JMX 3.3.0
    if server_dict.get('has_account'):
        del server_dict['has_account']

    if server_dict.get('account_name'):
        server_dict['jmxaccount'] = confidential_name()
    delete_server_fields_for_xml(server_dict)

    for key in server_dict:
        if key is None:
            server_dict[key] = ''

    server_et = ET.Element('jmxserver')

    for key in server_dict:
        if server_dict[key]:
            server_et.set(key, server_dict[key])

    out = ET.tostring(server_et, encoding='UTF-8')
    if sys.version_info > (3,):
        out = out.decode('utf-8')

    out = out[out.find('\n') + 1:]
    return out


def update_inputs(config_file_path_input_param, token):
    """
    Monitors jmx_tasks.conf and updates inputs.conf and jmxpoller xml configurations in case of modification made
    in jmx_tasks

    :param config_file_path_input_param: file path to store jmxpoller xml configurations
    :param token: splunk session key
    :return: None
    """
    config_manager_obj = conf_manager.ConfManager(token, APPNAME)
    templates = get_stanza_configuration(config_manager_obj, 'jmx_templates')
    tasks = get_stanza_configuration(config_manager_obj, 'jmx_tasks')
    input_conf_object = config_manager_obj.get_conf('inputs')
    inputs = input_conf_object.get_all(only_current_app=True)

    # Used splunkenv.get_conf_stanzas() instead of conf_manager.get_conf()
    # as second one requires realm to decrypt encrypted field and realm is depended on destination app
    # which we only get after reading servers configuration
    servers = splunkenv.get_conf_stanzas('jmx_servers')
    has_account_param_holding_server = list()

    for name in tasks:
        task = tasks[name]
        if task.get('servers'):
            server_names = task['servers'].replace(' ', '').split('|')
        else:
            LOGGER.error("No servers field found in {0}. Kindly verify your configuration for {0} in tasks.conf".format(task))
            continue
        if task.get('templates'):
            template_names = task['templates'].replace(' ', '').split('|')
        else:
            LOGGER.error("No template field found in {0}. Kindly verify your configuration for {0} in tasks.conf".format(task))
            continue

        check_data_duplication(server_names, template_names, tasks, name, LOGGER)

        mbeans_xml = ''
        for template_name in template_names:
            template_name = template_name.split(":")[1]
            template = templates.get(template_name)
            if template is None:
                LOGGER.error("No stanza named {} found in jmx_templates.conf. Kindly verify"
                             " template configurations".format(template_name))
                continue
            mbean_xml = decode(template['content'])
            if sys.version_info > (3,):
                mbean_xml = mbean_xml.decode('utf-8')
            mbeans_xml += mbean_xml + '\n'

        servers_xml = ''

        for server_name in server_names:
            server_name = server_name.split(":")[1]
            server = servers.get(server_name)

            if server_name not in has_account_param_holding_server and server.get('has_account') is not None:
                has_account_param_holding_server.append(server_name)
            if server is None:
                LOGGER.error("No stanza named {} found in jmx_servers.conf. Kindly verify"
                             " server configurations".format(server_name))
                continue
            servers_xml += get_server_dict_to_xml(server, server_name) + '\n'

        full_xml = '<jmxpoller>\n' \
                   '<formatter className="com.dtdsoftware.splunk.formatter.TokenizedMBeanNameQuotesStrippedFormatter" />\n' \
                   '<cluster name="cluster" description="A cluster">\n' \
                   '{}{}' \
                   '</cluster>\n' \
                   '</jmxpoller>\n'.format(mbeans_xml, servers_xml)

        input_name = JMX_INPUT_PREFIX + name

        if input_name in inputs:
            del inputs[input_name]

        config_file = '_{}.{}.{}.xml'.format(APPNAME, task.get('destinationapp'), name)

        input_stanza_config = {"config_file": config_file, "config_file_dir": config_file_path_input_param,
                               "polling_frequency": task['interval'], "sourcetype": task['sourcetype'],
                               "index": task['index'], "disabled": task['disabled']}

        config_manager_obj.get_conf("inputs").update(input_name, input_stanza_config)

        print(input_name, str(input_stanza_config))

        file_path = os.path.join(java_const.CONFIG_HOME, config_file)

        old_xml = ''
        try:
            with open(file_path, 'r') as f:
                old_xml = f.read()
        except:
            pass
        if old_xml != full_xml:
            try:
                with open(file_path, 'w') as f:
                    f.write(full_xml)
            except:
                pass

    if len(has_account_param_holding_server) > 0:
        LOGGER.warn('"has_account" parameter has been deprecated so kindly manually remove it from jmx_servers.conf for server stanza - [{}] '.format(",".join(has_account_param_holding_server)))

    # Delete jmx inputs for which tasks are not present in jmx_tasks.conf
    for name in inputs:
        if name == 'jmx':
            continue
        try:
            os.remove(os.path.join(java_const.CONFIG_HOME, inputs[name].config_file))
        except:
            pass
        input_conf_object.delete(name)
