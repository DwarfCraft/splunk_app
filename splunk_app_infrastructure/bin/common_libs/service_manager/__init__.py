from builtins import object


class BaseServiceManagerException(Exception):
    """
    Base exception class for all service manager related exceptions
    """
    def __init__(self, message):
        super(BaseServiceManagerException, self).__init__(message)


class BaseServiceManager(object):
    """
    BaseServiceManager class
    """

    def __init__(self):
        pass
