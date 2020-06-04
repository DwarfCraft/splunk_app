'''
The session module exports the session object that you can use to store and retrieve information in a thread-safe
manner.

Usage:
```code
from session import session
# save information to session
session.save(authtoken='abcdef', user='admin')
# read information from session
authtoken = session['authtoken'] # 'abcdef'
something_else = session['non_existent_key'] # None
# clear session
session.clear()
```
'''

from builtins import object
import threading
import functools
from .exception import BaseRestException
import http.client


class SessionAlreadyInitializedException(Exception):
    def __init__(self):
        super(SessionAlreadyInitializedException, self).__init__('session already initialized.')


class _LocalSession(object):
    '''
    _LocalSession is a wrapper class arounds the actual session object. It is
    thread-local so that race condition will be avoided during concurrent request handling

    It is a singleton class that should not be initialized outside of this module.
    '''
    _s_local = threading.local()
    _initialized = False

    def __init__(self):
        if _LocalSession._initialized:
            raise SessionAlreadyInitializedException()
        _LocalSession._initialized = True

    def __getitem__(self, name):
        return getattr(self._s_local, name, None)

    def save(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self._s_local, k, v)

    def clear(self):
        _LocalSession._s_local = threading.local()


# this is the session object that should be exported
session = _LocalSession()


class UnauthenticatedException(BaseRestException):
    def __init__(self, msg):
        super(UnauthenticatedException, self).__init__(http.client.UNAUTHORIZED, msg)


def authtoken_required(func):
    """
    Decorator util method that raises Exception if `authtoken` is not stored on current session.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not session['authtoken']:
            raise UnauthenticatedException('Authtoken not found in current session.')
        return func(*args, **kwargs)
    return wrapper
