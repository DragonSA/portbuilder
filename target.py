"""
The target module.  This module handles executing various stages for building
ports
"""
from __future__ import with_statement

from port import DependHandler, Port
from tools import invert
from queue import config_queue, fetch_queue, build_queue, install_queue

class Caller(object):
  from threading import Lock

  __lock = Lock()

  def __init__(self, count, callback):
    self.__count = count
    self.__callback = callback

  def __call__(self):
    with self.__lock:
      assert self.__count > 0
      self.__count -= 1
      if self.__count > 0:
        return
    if callable(self.__callback):
      self.__callback()

class Builder(object):
  """
     The Builder class.  This class handles building a particular stage
  """

  def __init__(self, stage, queue, prev_builder=None):
    from logging import getLogger
    from threading import Lock
    #: Logger for this Builder
    self.__name = Port.STAGE_NAME[stage]
    self.__lock = Lock()  #: Synchroniser lock for this builder
    self.__log = getLogger("pypkg.builder." + self.__name)
    self.__stage = stage  #: The stage we are taking care of
    self.__queue = queue  #: The queue for this stage
    self.__prev_builder = prev_builder  #: The builder for the previous stage

    self.__building = {}  #: List of ports we are working on

  def put(self, port, callback=None):
    port_lock = port.lock()
    if port.stage() < Port.CONFIG:
      config_builder(port, lambda: self(port, callback))
      return
    # Make sure the ports dependant handler has been created:
    depends = port.depends()
    with self.__lock:
      if self.__building.has_key(port):
        if callable(callback):
          self.__building[port].append(callback)
        return
      port_lock.acquire()
      stage = port.stage()
      if port.failed() or stage > self.__stage:
        port_lock.release()
        with invert(self.__lock):
          if callable(callback):
            callback()
          return
      elif stage < self.__stage - 1 or \
           (port.working() and stage == self.__stage - 1):
        port_lock.release()
        assert self.__prev_builder is not None
        with invert(self.__lock):
          self.__prev_builder(port, lambda: self(port, callback))
        return
      elif depends.check(self.__stage) > DependHandler.UNRESOLV:
        port_lock.release()
        self.__building[port] = callable(callback) and [callback] or []
        self.__queue.put(lambda: self.build(port))
        return

    depends = depends.dependancies(DependHandler.STAGE2DEPENDS[self.__stage])
    port_lock.release()

    callback = Caller(len(depends), lambda: self.put(port, callback))

    for i in depends:
      if i.status() == DependHandler.UNRESOLV:
        install_builder(i.port(), callback)
      else:
        callback()

  def __call__(self, port, callback=None):
    self.put(port, callback)

  def __len__(self):
    return len(self.__building)

  def build(self, port):
    assert self.__building.has_key(port)
    port.build_stage(self.__stage, False)
    with self.__lock:
      callbacks = self.__building.pop(port)
    for i in callbacks:
      i()

class Configer(object):
  from threading import Lock

  lock   = Lock()
  cache = {}

  def __init__(self, port, callback=None):
    self.__port = port
    self.__callback = callback
    self.__count = 1
    self.__callback = callable(callback) and [callback] or []

  def add_callback(self, callback):
    self.__callback.append(callback)

  def config(self):
    from port import ports
    assert self.__port.stage() < Port.CONFIG

    if self.__port.build_stage(Port.CONFIG, False):
      self.__count = len(self.__port.attr('depends')) + 1
      for i in self.__port.attr('depends'):
        port = ports[i]
        if port.stage() < Port.CONFIG:
          config_builder(port, self.finish)
        else:
          self.finish()
    self.finish()

  def finish(self):
    assert self.__count > 0
    with self.lock:
      self.__count -= 1
      if self.__count == 0:
        self.cache.pop(self.__port)
      else:
        return
    for i in self.__callback:
      i()

def config_builder(port, callback=None):
  if port.stage() < Port.CONFIG:
    with Configer.lock:
      if port.stage() < Port.CONFIG:
        if Configer.cache.has_key(port):
          Configer.cache[port].add_callback(callback)
        else:
          conf = Configer(port, callback)
          Configer.cache[port] = conf
          config_queue.put(conf.config)
        return
  if callable(callback):
    callback()

fetcher = Builder(Port.FETCH, fetch_queue)
def fetch_builder(port, callback=None, recurse=False):
  if recurse:
    if port.stage() < Port.CONFIG:
      config_builder(port, lambda: fetch_builder(port, callback, True))
      return

    depends = []
    new_depends = port.depends().dependancies()
    while len(new_depends):
      old_depends = new_depends
      new_depends = []
      for i in old_depends:
        for j in i.dependancies():
          if j not in depends:
            new_depends.append(j)
            depends.append(j)

    if callable(callback):
      callback = Caller(len(depends) + 1, callback)
    for i in depends:
      fetcher.put(i.port(), callback)
  fetcher.put(port, callback)

build_builder   = Builder(Port.BUILD, build_queue, fetch_builder)
install_builder = Builder(Port.INSTALL, install_queue, build_builder)
