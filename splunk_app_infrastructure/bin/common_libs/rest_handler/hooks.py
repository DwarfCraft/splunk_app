from abc import ABCMeta, abstractmethod
from future.utils import with_metaclass
from .rest_interface_splunkd import BaseRestInterfaceSplunkd

from logging_utils.log import getLogger

logger = getLogger()


class InvalidHookException(Exception):
    pass


class BeforeHandleHook(with_metaclass(ABCMeta)):
    """
    BeforeHandleHook is the abstract class for all hooks that should be executed before the
    actual handling of an incoming request. Subclass of this class must implement the `before_handle`
    method for it to be executed.
    """

    def execute(self, request):
        logger.info('Start executing before handle hook - %s' % self.__class__.__name__)
        self.before_handle(request)
        logger.info('Finished executing before handle hook - %s' % self.__class__.__name__)

    @abstractmethod
    def before_handle(self, request):
        """
        this method is invoked before the actual handling of the incoming request.
        The request object is passed in as argument, and this hook can be used to augment the request
        object or run additional validation.
        """
        pass


def before_handle_hooks(hooks):
    """
    Decorator method for subclass of rest_interface_splunkd.BaseRestInterfaceSplunkd. Hooks passed
    into this decorator will be invoked in the order they are defined before handling any requests sent
    to the rest interface class decorated.

    :param hooks: hooks to be executed
    :type hooks: subclass of BeforeHandleHook
    """
    for hookCls in hooks:
        if not issubclass(hookCls, BeforeHandleHook):
            raise InvalidHookException('Invalid hook registered - %s' % hookCls.__name__)

    def register_hooks(cls):
        if not issubclass(cls, BaseRestInterfaceSplunkd):
            raise InvalidHookException('Invalid class for hooks - %s' % cls.__name__)
        cls._registered_before_handle_hooks = getattr(cls, '_registered_before_handle_hooks', [])
        for hookCls in hooks:
            hook = hookCls()
            cls._registered_before_handle_hooks.append(hook)

        return cls
    return register_hooks
