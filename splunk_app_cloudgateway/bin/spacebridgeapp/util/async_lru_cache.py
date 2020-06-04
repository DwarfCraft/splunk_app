"""
(C) 2020 Splunk Inc. All rights reserved.

A Twisted friendly version of functools.lru_cache.
"""
import collections
import functools
import itertools

from twisted.internet import defer


DEFAULT_CACHE_SIZE = 64


# TODO: When we switch to asyncio for py3 + splexit, this will no longer work and we'll need to migrate over to using
#       something like this: https://pypi.org/project/aiocache


def memoize(func):
    """A decorator that caches results for functions that use defer.inlineCallbacks with a least recently used cache.

    NOTE: This only works for functions with parameter values that are hashable. Make sure not to use this with mutable
          collections like lists and dictionaries or other classes that do not implement __hash__ and __eq__.

    Usage:

        @async_lru_cache
        @defer.inlineCallbacks
        def my_expensive_function(some_arg, some_keyword_arg=None):
            # do a bunch of network calls...
            defer.returnValue(results)

        first = yield my_expensive_function(some_arg, some_keyword_arg=my_param)   # cache miss (slow)
        second = yield my_expensive_function(some_arg, some_keyword_arg=my_param)  # cache hit (fast)
        third = yield my_expensive_function(some_arg, some_keyword_arg=my_param)   # cache hit (fast)
    """
    if _DISABLE_FOR_TEST:
        return func

    cache = AsyncLRUCache()

    @defer.inlineCallbacks
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = yield cache.get(func, *args, **kwargs)
        defer.returnValue(result)
    return wrapper


class AsyncLRUCache(object):
    """A least recently used cache for use with twisted defer.inlineCallbacks functions."""

    def __init__(self, max_size=DEFAULT_CACHE_SIZE):
        """
        :param max_size: an integer determining how many unique argument combinations to remember. Ideally this will be
                         the the same as the expected number of concurrent requests or callers of the function to be
                         cached.
        """
        self._args_to_results = collections.OrderedDict()
        self._max_size = max_size

    @defer.inlineCallbacks
    def get(self, func, *args, **kwargs):
        """Returns the cached result of calling func(*args, **kwargs) or computes it if there is no stored result."""
        arg_key = _get_args_key(func, args, kwargs)
        if arg_key in self._args_to_results:
            result = self._args_to_results[arg_key]
            del self._args_to_results[arg_key]
            self._args_to_results[arg_key] = result
            defer.returnValue(result)

        result = yield func(*args, **kwargs)
        self._args_to_results[arg_key] = result
        if len(self._args_to_results) > self._max_size:
            oldest_key = next(iter(self._args_to_results))
            del self._args_to_results[oldest_key]

        defer.returnValue(result)


def _get_args_key(func, args, kwargs):
    kwargs = sorted(kwargs.items()) if kwargs else []
    combined_args = itertools.chain([func], args or [], kwargs)
    return hash(tuple(combined_args))


# Utilities for turning on and off caching during tests.
_DISABLE_FOR_TEST = False


def enable_cache_for_testing():
    """This should not be called by tests aside from test_async_lru_cache.py"""
    global _DISABLE_FOR_TEST
    _DISABLE_FOR_TEST = False


def disable_cache_for_testing():
    """Many of our tests use the same constant across test cases. This is so we can still do this if"""
    global _DISABLE_FOR_TEST
    _DISABLE_FOR_TEST = True
