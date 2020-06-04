'''
This module overwrites the i18n.ugettext and i18n.ungettext method if it's not present
'''
import sys

if sys.version_info < (3, 0):
    import __builtin__
else:
    import builtins
    __builtin__ = builtins


def ugettext(message):
    """
    NOTE: this is a stub method for i18n.ugettext

    Translate a string message
    This method is also installed as "_" in builtins
    """
    return message


def ungettext(msgid1, msgid2, n):
    """
    NOTE: this is a stub method for i18n.ungettext

    Translate a string message with a number in it
    """
    return msgid1 if n == 1 else msgid2


try:
    from splunk.appserver.mrsparkle.lib import i18n
    i18n.ugettext('test')  # try it out to check if it's functional
    ugettext = i18n.ugettext  # noqa
    ungettext = i18n.ungettext  # noqa
except Exception:
    '''No working i18n available - will use stubs for ugettext and ungettext'''

_ = ugettext
__builtin__.__dict__['_'] = _
__builtin__.__dict__['ungettext'] = ungettext
