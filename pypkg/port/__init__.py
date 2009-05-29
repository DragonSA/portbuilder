"""
The Port module.  This module contains all classes and utilities needed for
managing port information.
"""
from __future__ import absolute_import

from .port import Port
from .dependhandler import DependHandler
from .cache import PortCache

__all__ = ['cache', 'get', 'Port', 'DependHandler']

#: A cache of ports available with auto creation features
cache = PortCache()
get = cache.get  #: Alias for port_cache.get
