import em_path_inject  # noqa
from logging_utils import log

logger = log.getLogger()


class EmException(Exception):
    """
    General exception class for all internal EM classes
    """
    def __init__(self, message):
        super(EmException, self).__init__(message)
        self.message = message
        logger.error(message)


class VictorOpsCouldNotSendAlertException(EmException):

    def __init__(self, message):
        super(VictorOpsCouldNotSendAlertException, self).__init__(message)


class VictorOpsNotExistException(EmException):

    def __init__(self, message):
        super(VictorOpsNotExistException, self).__init__(message)


class WebhookCouldNotSendAlertException(EmException):

    def __init__(self, message):
        super(WebhookCouldNotSendAlertException, self).__init__(message)


class SlackCouldNotSendAlertException(EmException):

    def __init__(self, message):
        super(SlackCouldNotSendAlertException, self).__init__(message)


class ArgValidationException(EmException):

    def __init__(self, message):
        super(ArgValidationException, self).__init__(message)
