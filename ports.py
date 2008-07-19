"""
The Port module.  This module contains all classes and utilities needed for
managing port information.  
"""

from __future__ import with_statement # Used for locking

ports = {}  #: A cache of ports available with auto creation features
ports_dir = "/usr/ports/"  #: The location of the ports tree

class Port(object):
  """
     The class that contains all information about a given port, such as status,
     dependancies and dependants
  """

  def __init__(self, origin):
    """
       Initialise the port and all its information

       @param origin: The ports origin (within the ports tree)
       @type origin: C{str}
    """
    self._origin = origin               #: The origin of the port
    self._depends = get_depends(origin)  #: A list of all dependancies (Port's)

class PortCache(dict):
  """
     The PortCache class.  This class keeps a cache of Port objects
     (note: this is an inflight cache)
  """

  def __init__(self, **args):
    """
       Initialise the cache of ports
    """
    dict.__init__(self, **args)

    from threading import RLock
    self._lock = RLock()

  def __getitem__(self, key):
    """
       Retrieve a port by name.  If the work does not exist then it is queued
       for construction.  The method waits for the port to be constructed then
       returns the port

       @param key: The port to retrieve
       @type key: C{str}
       @return: The port requested
       @rtype: C{Port}
    """
    from queue import ports_queue

    with self._lock:
      try:
        value = dict.__getitem__(self, key)
      except KeyError:
        self.add(key)
        value = None
      if not value:
        self._lock.release()
        ports_queue.join()
        self._lock.acquire()

        value = dict.__getitem__(self, key)
        if not value:
          # TODO: critical error
          raise KeyError, key
      return value

  def __setitem__(self, key, value):
    """
       Records a port in the cache

       @param key: The ports name
       @type key: C{str}
       @param value: The port object
       @type value: C{str}
    """
    with self._lock:
      dict.__setitem__(self, key, value)

  def add(self, key):
    """
       Adds a port to be contructed if not already in the cache or queued for
       construction
    """
    from queue import ports_queue
    with self._lock:
      if not self.has_key(key):
        self[key] = None
        ports_queue.put_nowait((self.get, [key]))

  def get(self, k):
    """
       Get a port.  If the port is not in the cache then created it (whereas
       __getitem__ would queue the port to be constructed).  Use this if the
       port requested is a once of request

       @param k: The port to get
       @type k: C{str}
       @return: The port
       @rtype: C{Port}
    """
    with self._lock:
      try:
        value = dict.__getitem__(self, k)
        if value:
          return value
      except KeyError:
        self[k] = None

    # Time consuming task, done outside lock
    port = Port(k)

    with self._lock:
      value = dict.__getitem__(self, k)
      if not value:
        self[k] = port
        value = port
      return value

ports = PortCache()

def get_depends(origin):
  """
     Retrieve a list of dependants given the ports origin

     @param origin: The port identifier
     @type origin: C{str}
     @return: A list of dependentant ports
     @rtype: C{[Port]}
  """
  from subprocess import Popen, PIPE

  make = Popen(['make', '-C', ports_dir + origin, '-V', '_DEPEND_DIRS'],
               stdout=PIPE)
  make.wait()
  depends = [i[len(ports_dir):] for i in make.stdout.read().split()]

  for i in depends:
    ports.add(i)

  return depends
