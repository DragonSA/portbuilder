"""
The target module.  This module handles executing various stages for building
ports
"""
from __future__ import with_statement

from contextlib import nested
from tools import invert

class Builder(object):
  """
     The Builder class.  This class handles building a particular stage
  """

  def __init__(self, stage, queue, pre_builder=None):
    from logging import getLogger
    from threading import Lock
    #: Logger for this Builder
    self.__name = Port.STAGE_NAME[stage]
    self.__lock = Lock()  #: Synchroniser lock for this builder
    self.__log = getLogger("pypkg.builder." + self.__name)
    self.__stage = stage  #: The stage we are taking care of
    self.__queue = queue  #: The queue for this stage
    self.__pre_builder = pre_builder  #: The builder for the previous stage

    self.__working = []  #: List of ports we are working on

  def append(self, port, callback=None):
    if callback is None or not callable(callback):
      def caller():
        pass
      callback = caller
    # TODO: Check if not configured, if not then make sure it is
    port_lock = port.lock()
    port_lock.acquire()
    with self.__lock:
      if port.failed() or port.stage() > self.__stage:
        with invert(self.__lock):
          port_lock.release()
          callback()
          return
      if port.working():
        if port.stage() == self.__stage:
          if not self.__working.has_key(port):
            self.__log.error("Port '%s' not being built via this Builder"
                            % port.origin())
          else:
            self.__working[port].append(callback)
          port_lock.release()
          return
      if port.stage() < self.__stage:
        port_lock.release()
        if self.__pre_builder:
          self.__pre_builder.append(port, lambda: self.__build(port))
        else:
          self.__log.error("Unable to resolve stage '%s' of port '%s'"
                           % (self.__name, port.origin()))
          return

      # TODO: Fix
      for i in port.depends().dependancies(DependHandler.???self.__stage):
        if i.status() == DependHandler.UNRESOLV:
          install_builder.append(i.port(), lambda: self.__cond_append(port,
                                                                      callback))

  def __cond_append(self, port, callback):
    for i in port.depends().dependancies(DependHandler.???self.__stage):
      if i.status() == DependHandler.UNRESOLV:
        return
    self.append(port, callback)

  def __build(self, port):
    assert self.__building.has_key(port)
    port.build(self.__stage)
    for i in self.__building(port):
      i()
    with self.__lock:
      self.__building.pop(port)
