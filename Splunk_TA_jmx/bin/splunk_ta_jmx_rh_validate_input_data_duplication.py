import import_declare_test
import splunk.admin as admin
from solnlib import log
from solnlib import splunkenv

from splunk_ta_jmx_utility import check_data_duplication

log.Logs.set_context()
logger = log.Logs().get_logger("ta_jmx_rh_input_data_duplication")


class InputDataDuplicationValidationHandler(admin.MConfigHandler):
    """
    REST Endpoint to validate data duplication occurs or not
    """

    def setup(self):
        """
        This method checks which action is getting called and what parameters are required for the request.
        :return: None
        """
        if self.requestedAction == admin.ACTION_LIST:
            # Add required args in supported args
            for arg in ("templates", "servers", "input_name"):
                self.supportedArgs.addReqArg(arg)

    def handleList(self, conf_info):
        """
        This handler is to validate the if the input configuration is valid or not
        It takes  ("servers", "templates", "input_name") as caller args and
         Returns the confInfo dict object in response.
        :param conf_info: response dict
        :return: None
        """

        logger.debug("Entering handler to check input configuration")
        # Get args parameters from the request
        templates = self.callerArgs.data['templates'][0].replace(' ', '').split('|')
        servers = self.callerArgs.data['servers'][0].replace(' ', '').split('|')
        input_name = self.callerArgs.data['input_name'][0]
        stanzas = splunkenv.get_conf_stanzas('jmx_tasks')

        conf_info[input_name]['duplicate_warning'] = check_data_duplication(servers, templates, stanzas, input_name,
                                                                            logger)


if __name__ == "__main__":
    admin.init(InputDataDuplicationValidationHandler, admin.CONTEXT_APP_AND_USER)
