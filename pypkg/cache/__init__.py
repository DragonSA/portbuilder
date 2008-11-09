"""
The Cache module.  This module stores various items of information statically.
"""
from __future__ import absolute_import

from pypkg.cache.cachedb import CacheDB

__all__ = ['db']

db = CacheDB()  #: The databases used for caching
