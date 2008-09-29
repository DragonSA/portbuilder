"""
The target module.  This module handles executing various stages for building
ports
"""
from __future__ import with_statement

from port import DependHandler, Port
from tools import invert
from queue import config_queue, fetch_queue, build_queue, install_queue

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

  def __call__(self, port, callback=None):
    port_lock = port.lock()
    if port.stage() < Port.CONFIG:
      config_builder(port, lambda: self(port, callback))
      return
    # Make sure the ports dependant handler has been created:
    depends = port.depends()
    port_lock.acquire()
    with self.__lock:
      if port.failed() or port.stage() > self.__stage:
        with invert(self.__lock):
          port_lock.release()
          if callable(callback):
            callback()
          return
      elif port.stage() < self.__stage:
        port_lock.release()
        if self.__prev_builder:
          with invert(self.__lock):
            self.__prev_builder(port, lambda: self(port, callback))
        else:
          self.__log.error("Unable to resolve stage '%s' of port '%s'"
                           % (self.__name, port.origin()))
          return
      elif port.working():
        port_lock.release()
        # Implied: port.stage() == self.__stage:
        if not self.__building.has_key(port):
          self.__log.error("Port '%s' not being built via this Builder"
                           % port.origin())
        elif callable(callback):
          self.__building[port].append(callback)
        return
      elif depends.check(self.__stage) > DependHandler.UNRESOLV:
        port_lock.release()
        self.__building[port] = callable(callback) and [callback] or []
        with invert(self.__lock):
          self.__queue.put(lambda: self.__build(port))
        return

    depends = depends.dependancies(DependHandler.STAGE2DEPENDS[self.__stage])
    port_lock.release()

    for i in depends:
      if i.status() == DependHandler.UNRESOLV:
        install_builder(i.port(), lambda: self.__cond_call(port, callback))

  def __cond_call(self, port, callback):
    for i in port.depends().dependancies(
               DependHandler.STAGE2DEPENDS[self.__stage]):
      if i.status() == DependHandler.UNRESOLV:
        return
    self(port, callback)

  def __build(self, port):
    assert self.__building.has_key(port)
    port.build(self.__stage)
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
    if self.__port.build(Port.CONFIG):
      self.__count = len(self.__port.attr('depends'))
      for i in self.__port.attr('depends'):
        config_builder(ports[i], self.finish)
    self.finish()

  def finish(self):
    with self.lock:
      if self.__count > 1:
        self.__count -= 1
        return
      else:
        self.cache.pop(self.__port.origin())
    for i in self.__callback:
      i()

def config_builder(port, callback=None):
  with Configer.lock:
    if Configer.cache.has_key(port):
      Configer.cache[port].add_callback(callback)
    else:
      conf = Configer(port, callback)
      Configer.cache[port] = conf
      config_queue.put(conf.config)

fetch_builder   = Builder(Port.FETCH, fetch_queue)
build_builder   = Builder(Port.BUILD, build_queue, fetch_builder)
install_builder = Builder(Port.INSTALL, install_queue, build_builder)