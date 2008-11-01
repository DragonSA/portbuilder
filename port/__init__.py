"""
The Port module.  This module contains all classes and utilities needed for
managing port information.
"""
from dependhandler import DependHandler
from port import Port
from portcache import PortCache

__all__ = ['port_cache', 'get', 'Port', 'DependHandler']

#: A cache of ports available with auto creation features
port_cache = PortCache()
get = port_cache.get  #: Alias for port_cache.get
