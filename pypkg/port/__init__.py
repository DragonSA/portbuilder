"""
The Port module.  This module contains all classes and utilities needed for
managing port information.
"""
from __future__ import absolute_import

from pypkg.port.port import Port
from pypkg.port.dependhandler import DependHandler
from pypkg.port.portcache import PortCache

__all__ = ['cache', 'get', 'Port', 'DependHandler']

#: A cache of ports available with auto creation features
cache = PortCache()
get = cache.get  #: Alias for port_cache.get
