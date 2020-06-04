"""
(C) 2019 Splunk Inc. All rights reserved.

ContextLogger override a standard Python Logger to append request_context to end of log events
"""
import sys
import os
import logging
from twisted.python import context


def add_ctx(msg):
    """
    Helper method used to append the context string to the end of a msg
    :param msg:
    :return:
    """
    request_context = context.get("request_context")
    log_msg = "{} {}".format(msg, request_context) if request_context else msg
    return log_msg


class ContextLogger(logging.Logger):

    def __init__(self, name, level=logging.NOTSET):
        return super(ContextLogger, self).__init__(name, level)

    def findCaller(self):
        """
        Find the stack frame of the caller so that we can note the source
        file name, line number and function name.
        """
        f = sys._getframe(3)
        if f is not None:
            f = f.f_back
        rv = "(unknown file)", 0, "(unknown function)"
        while hasattr(f, "f_code"):
            co = f.f_code
            filename = os.path.normcase(co.co_filename)
            if filename ==  __file__:
                f = f.f_back
                continue
            rv = (co.co_filename, f.f_lineno, co.co_name)
            break
        return rv

    def exception(self, msg, *args, **kwargs):
        super(ContextLogger, self).exception(add_ctx(msg), *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        super(ContextLogger, self).error(add_ctx(msg), *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        super(ContextLogger, self).warning(add_ctx(msg), *args, **kwargs)

    warn = warning

    def info(self, msg, *args, **kwargs):
        super(ContextLogger, self).info(add_ctx(msg), *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        super(ContextLogger, self).debug(add_ctx(msg), *args, **kwargs)


# This replaces the usages of the default logging class
logging.setLoggerClass(ContextLogger)
