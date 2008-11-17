"""
The port cache module.  This module contains the cache of active ports.
"""
from __future__ import absolute_import, with_statement

__all__ = ['PortCache']

class PortCache(dict):
  """
     The PortCache class.  This class keeps a cache of Port objects
     (note: this is an inflight cache).
  """
  from logging import getLogger

  _log = getLogger('pypkg.cache')  #: Logger for this cache

  def __init__(self):
    """
       Initialise the cache of ports.
    """
    dict.__init__(self)

    from threading import Condition, Lock

    self.__dead_cnt = 0  #: The number of 'bad' ports
    self.__lock = Condition(Lock())  #: The lock for this cache

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
       returns the port.

       @param key: The port to retrieve
       @type key: C{str}
       @return: The port requested
       @rtype: C{Port}
    """
    key = self._normalise(key)      # Make sure the port is named properly
    with self.__lock:
      # Try get the port.  If we have it return, if it is known not to exist
      # then raise a KeyError.
      try:
        value = dict.__getitem__(self, key)
        if value:
          return value
      except KeyError:
        # Port does not exist, ask for it to be created
        self.__add(key)
      else:
        if value is False:
          raise KeyError, key

      # We do not have the port, wait for it to be created
      while True:
        self.__lock.wait()
        # Null refernce of the port already added, can ignore it
        value = dict.__getitem__(self, key)
        if value is not None:
          if value:
            return value
          else:
            raise KeyError, key

  def __setitem__(self, key, value):
    """
       Records a port in the cache.

       @param key: The ports name
       @type key: C{str}
       @param value: The port object
       @type value: C{str}
    """
    key = self._normalise(key)  # Make sure the port is named properly
    with self.__lock:
      dict.__setitem__(self, key, value)

  def has_key(self, k):
    """
       Check if a port exists.

       @param k: The ports origin
       @type k: C{str}
       @return: If the port exists
       @rtype: C{bool}
    """
    # TODO: Needed? with DictMixin (when convert to it?)
    try:
      PortCache.__getitem__(self, k)
      return True
    except KeyError:
      return False

  def add(self, key):
    """
       Adds a port to be contructed if not already in the cache or queued for
       construction.

       @param key: The port for queueing
       @type key: C{str}
       @return: The job ID of the queued port
       @rtype: C{int}
    """
    key = self._normalise(key)  # Make sure the port is named properly
    with self.__lock:
      self.__add(key)

  def __add(self, key):
    """
       Adds a port to be constructed (requires lock to be held).

       @param key: The port for queueing
       @type key: C{str}
       @return: The job ID of the queued port
       @rtype: C{int}
    """
    # NOTE: Needs to be called with lock held and key normalised
    assert not self.__lock.acquire(False)

    # We allow multiple calls to add and thus so must __add
    if not dict.has_key(self, key):
      from pypkg.queue import ports_queue

      dict.__setitem__(self, key, None)
      self.__dead_cnt += 1  # Reference count to offset 'bad' ports

      return ports_queue.put_nowait(lambda: self.__get(key))

  def get(self, key, default=None):
    """
       Get a port from the database.

       @param key: The ports origin
       @type key: C{str}
       @param default: The default argument
       @return: The port or None
       @rtype: C{Port}
    """
    # TODO: Needed? with DictMixin
    try:
      return self[key]
    except KeyError:
      return default

  def __get(self, key):
    """
       Create a port and add it to the database.

       @param key: The port to get
       @type key: C{str}
    """
    from os.path import isdir, join

    from pypkg.make import env
    from pypkg.port import Port

    try: # Time consuming task, done outside lock
      # Check the port actually exists before doing heavy work
      if isdir(join(env['PORTSDIR'], key)) and len(key.split('/')) == 2:
        port = Port(key)
        self._log.debug("Created port: %s" % key)
      else:
        port = False  # Port does not exist
        self._log.error("Invalid port name or port does not exist: %s" % key)
    except KeyboardInterrupt:
      raise
    except BaseException:
      port = False  # Could not create port, exception
      self._log.exception("Error while creating port: %s" % key)

    with self.__lock:
      dict.__setitem__(self, key, port)
      if port:
        self.__dead_cnt -= 1  # We now have a live port
      self.__lock.notifyAll()  # May have some methods waiting for this port

  def _normalise(self, origin):
    """
       Normalise the name of a port.

       @param origin: The current name of the port
       @type origin: C{str}
       @return: The normalised name of the port
       @rtype: C{str}
    """
    from os import sep

    new = origin.strip().rstrip(sep).split(sep)
    index = 0
    while index < len(new):
      if new[index] in ('.', ''):
        new.pop(index)
      elif new[index] == '..':
        if index == 0:
          self._log.warn("Port name escapes port directory: %s" % origin)
          return origin
        new.pop(index)
        new.pop(index - 1)
        index -= 1
      else:
        index += 1

    new = sep.join(new)
    if new != origin:
      self._log.warn("Non standard port name used: %s" % origin)
    return new
