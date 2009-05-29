"""
The architecture module.  This module contains the architecture specific code.
"""
from __future__ import absolute_import

from logging import getLogger

from .freebsd_ports import get_attr, get_status as status

__all__ = ['attr', 'status']

log = getLogger('pypkg.port.arch')  #: Logger for this module

def attr(origin):
  """
     Retrieves the attributes for a given port, using the cached version when
     possible.

     @param origin: The port identifier
     @type origin: C{str}
     @return: A dictionary of attributes
     @rtype: C{\{str:str|(str)\}}
  """
  from ...cache import db, check_files, set_files
  from ...make import env

  # Only use cache if ports will not be modified (via WITH(OUT)_*)
  if not len([i for i in env.iterkeys() if i.startswith('WITH')]):
    # If the files have not been changes then use the cache
    if check_files('port.makefiles', origin):
      try:
        return db['port.attr'][origin]
      except KeyError:
        getLogger('pypkg.cache').warn('Corrupt data detected: port.attr.%s' %
                                                                        origin)

    # Get the port attributes the hard way
    att = get_attr(origin)

    log.info("Caching port attributes: %s" % origin)

    # Save the attributes in the cache
    db['port.attr'][origin] = att

    # Record the dependening makefiles details
    set_files('port.makefiles', origin, att['makefiles'])
    return att
  else:
    return get_attr(origin)
