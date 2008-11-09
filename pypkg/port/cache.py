"""
The port cache module.  This module contains the cache of active ports
"""
from __future__ import absolute_import, with_statement

__all__ = ['PortCache']

class PortCache(dict):
  """
     The PortCache class.  This class keeps a cache of Port objects
     (note: this is an inflight cache)
  """
  from logging import getLogger

  _log = getLogger('pypkg.cache')  #: Logger for this cache

  def __init__(self):
    """
       Initialise the cache of ports
    """
    dict.__init__(self)

    from threading import Condition, Lock

    self._lock = Condition(Lock())  #: The lock for this cache
    self.__dead_cnt = 0  #: The number of 'bad' ports

  def __len__(self):
    """
       The number of ports loaded.

       @return: Number of ports
       @rtype: C{int}
    """
    return dict.__len__(self) - self.__dead_cnt

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
    key = self._normalise(key)
    with self._lock:
      try:
        value = dict.__getitem__(self, key)
        if value:
          return value
      except KeyError:
        self.__add(key)
      else:
        if value is False:
          raise KeyError, key

      while True:
        if dict.has_key(self, key) and dict.__getitem__(self, key) != None:
          value = dict.__getitem__(self, key)
          if value:
            return value
          else:
            raise KeyError, key
        self._lock.wait()

  def __setitem__(self, key, value):
    """
       Records a port in the cache

       @param key: The ports name
       @type key: C{str}
       @param value: The port object
       @type value: C{str}
    """
    key = self._normalise(key)
    with self._lock:
      dict.__setitem__(self, key, value)

  def has_key(self, k):
    """
       Check if a port exists

       @param k: The ports origin
       @type k: C{str}
       @return: If the port exists
       @rtype: C{bool}
    """
    k = self._normalise(k)
    try:
      PortCache.__getitem__(self, k)
      return True
    except KeyError:
      return False

  def add(self, key):
    """
       Adds a port to be contructed if not already in the cache or queued for
       construction

       @param key: The port for queueing
       @type key: C{str}
       @return: The job ID of the queued port
       @rtype: C{int}
    """
    key = self._normalise(key)
    with self._lock:
      self.__add(key)

  def __add(self, key):
    """
       Adds a port to be constructed (requires lock to be held)

       @param key: The port for queueing
       @type key: C{str}
       @return: The job ID of the queued port
       @rtype: C{int}
    """
    if not dict.has_key(self, key):
      from pypkg.queue import ports_queue
      dict.__setitem__(self, key, None)
      self.__dead_cnt += 1
      return ports_queue.put_nowait(lambda: self._get(key))

  def get(self, key, default=None):
    """
       Get a port from the database.

       @param key: The ports origin
       @type key: C{str}
       @param default: The default argument
       @return: The port or None
       @rtype: C{Port}
    """
    try:
      return self[key]
    except KeyError:
      return default

  def _get(self, key):
    """
       Create a port and add it to the database

       @param key: The port to get
       @type key: C{str}
    """
    from os.path import isdir, join

    from pypkg.make import env
    from pypkg.port import Port

    try:
      # Time consuming task, done outside lock
      if isdir(join(env['PORTSDIR'], key)) and len(key.split('/')) == 2:
        port = Port(key)
      else:
        port = False
        self._log.error("Invalid port name '%s' passed" % key)
      self._lock.acquire()
    except KeyboardInterrupt:
      raise
    except BaseException:
      self._lock.acquire()
      port = False
      self._log.exception("Error while creating port '%s'" % key)
    dict.__setitem__(self, key, port)
    if port:
      self.__dead_cnt -= 1
    self._lock.notifyAll()
    self._lock.release()

  def _normalise(self, origin):
    """
       Normalise the name of a port

       @param origin: The current name of the port
       @type origin: C{str}
       @return: The normalised name of the port
       @rtype: C{str}
    """
    from os import sep
    new = origin.strip().rstrip('/').split('/')
    index = 0
    while index < len(new):
      if new[index] in ('.', ''):
        new.pop(index)
      elif new[index] == '..':
        if index == 0:
          self._log.warn("Port name escapes port directory: '%s'" % origin)
          return origin
        new.pop(index)
        new.pop(index - 1)
        index -= 1
      else:
        index += 1

    new = sep.join(new)
    if new != origin:
      self._log.warn("Non standard port name used: '%s'" % origin)
    return new
