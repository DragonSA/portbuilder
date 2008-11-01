"""
The target module.  This module handles executing various stages for building
ports.  
"""
from __future__ import absolute_import, with_statement

from pypkg.port import DependHandler, Port
from pypkg.queue import config_queue, fetch_queue, build_queue, install_queue

class Caller(object):
  """
     The Caller class.  This class provides a counted callback (similar to a
     Semaphore).  Once the count gets to 0 the callback is called.
  """
  from threading import Lock

  __lock = Lock()

  def __init__(self, count, callback):
    """
       Create a Caller with the given count and callback

       @param count: The number of calls until callback
       @type count: C{int}
       @param callback: The callback function/method/class
       @type callback: C{callable}
    """
    self.__count = count
    self.__callback = callback

  def __call__(self):
    """
       A call, when call count gets to *count* then a callback is called
    """
    with self.__lock:
      assert self.__count > 0
      self.__count -= 1
      if self.__count > 0:
        return
    if callable(self.__callback):
      self.__callback()

class StageBuilder(object):
  """
     The StageBuilder class.  This class handles building a particular stage
  """

  def __init__(self, stage, queue, prev_builder=None):
    """
       Create a target builder for a given stage using a given queue.  Also, if
       a previous stage is handled by a builder then use that builder to for the
       previous stages.

       @param stage: The stage this builder handles
       @type stage: C{int}
       @param queue: The queue to use for this stage
       @type queue: C{WorkerQueue}
       @param prev_builder: The builder for the previous stage
       @type prev_builder: C{callable}
    """
    from logging import getLogger
    from threading import Lock
    self.__lock = Lock()  #: Synchroniser lock for this builder
    #: Logger for this builder
    self.__log = getLogger("pypkg.target." + Port.STAGE_NAME[stage])
    self.__stage = stage  #: The stage we are taking care of
    self.__queue = queue  #: The queue for this stage
    self.__prev_builder = prev_builder  #: The builder for the previous stage

    self.__building = {}  #: List of ports we are working on
    self.__queues = ([], [], [])  #: The location of the queues
                                  # (active, queued, plending)

  def put(self, port, callback=None):
    """
       Place a port on the queue to be build.  When the port has finished call
       the given callback.

       @param port: The port to build
       @type port: C{Port} or C{str}
       @param callback: The callback function
       @type callback: C{callable}
    """
    if isinstance(port, str):
      from pypkg.port import get
      port = get(port)
      if not port:
        if callable(callback):
          callback()
        return
    port_lock = port.lock()
    if port.stage() < Port.CONFIG:
      config_builder(port, lambda: self.put(port, callback))
      return
    # Make sure the ports dependant handler has been created:
    with self.__lock:
      if self.__building.has_key(port):
        if callable(callback):
          self.__building[port].append(callback)
        return

      depends = port.depends()  # Needs to be done outside of port_lock
      port_lock.acquire()
      stage = port.stage()
      if port.failed() or stage >= self.__stage:
        port_lock.release()
        if callable(callback):
          try:
            self.__lock.release()
            callback()
          finally:
            self.__lock.acquire()
        return

      self.__building[port] = callable(callback) and [callback] or []
      self.__queues[2].append(port)
      if stage < self.__stage - 1 or \
           (port.working() and stage == self.__stage - 1):
        assert self.__prev_builder is not None
        resolv_depends = False
      elif depends.check(self.__stage) > DependHandler.UNRESOLV:
        port_lock.release()
        try:
          self.__lock.release()
          self.queue(port)
        finally:
          self.__lock.acquire()
        return
      else:
        resolv_depends = True

      depends = depends.dependancies(DependHandler.STAGE2DEPENDS[self.__stage])
      port_lock.release()

    callback = Caller(len(depends) + (resolv_depends and 0 or 1),
                      lambda: self.queue(port))

    for i in depends:
      if i.status() == DependHandler.UNRESOLV:
        install_builder(i.port(), callback)
      else:
        callback()

    if not resolv_depends:
      self.__prev_builder(port, callback)

  def build(self, port):
    """
       Build a port, given that it is on our queue.  Once the port has completed
       then the callback functions for the port are called.

       @param port: The port to build
       @type port: C{Port}
    """
    assert self.__building.has_key(port)
    with self.__lock:
      self.__queues[1].remove(port)
      self.__queues[0].append(port)
    port.build_stage(self.__stage, False)
    self.__callbacks(port)
    
  def queue(self, port):
    """
       Place a port on the queue (this is for delayed queueing).

       @param port: The port to place on the queue
       @type port: C{Port}
    """
    assert self.__building.has_key(port)
    with self.__lock:
      self.__queues[2].remove(port)
      self.__queues[1].append(port)
    if not port.failed():
      if port.depends().check(self.__stage) == DependHandler.FAILURE:
        self.__callbacks(port, 1)
      else:
        assert port.depends().check(self.__stage) > DependHandler.UNRESOLV
        assert port.stage() == self.__stage - 1 and not port.working()
        self.__queue.put(lambda: self.build(port))
    else:
      self.__callbacks(port, 1)

  def stats(self):
    """
       The statistics about the ports in the queue.  If the ports are active
       (i.e. building), queued to be active or waiting for another port...

       @return: The list of ports (active, queued, pending)
       @rtype: C{([Port], [Port], [Port])}
    """
    from copy import copy
    with self.__lock:
      return (copy(self.__queues[0]), copy(self.__queues[1]),
              copy(self.__queues[2]))

  def __call__(self, port, callback=None):
    """
       Alias for .put() [See TargetBuilder.put].
    """
    self.put(port, callback)

  def __len__(self):
    """
       Returns the number of ports waiting to be built.

       @return: The number of ports
       @rtype: C{int}
    """
    return len(self.__building)

  def __callbacks(self, port, queue=0):
    """
       Call the callback functions for a given port.

       @param port: The port
       @type port: C{Port}
       @param queue: The queue this port currently resides
       @type queue: C{int}
    """
    with self.__lock:
      callbacks = self.__building.pop(port)
      self.__queues[queue].remove(port)
    for i in callbacks:
      i()

class Configer(object):
  """
     The Configer class.  This class configures a port and all of its
     dependancies.
  """
  from threading import Lock

  lock  = Lock()  #: The global lock for this class
  cache = {}  #: Cache of Ports that are currently being configured

  def __init__(self, port, callback=None):
    """
       Create a configurer for a port.  Once the port (and all of its
       dependancies) have been configured then call a callback.

       @param port: The port to configure
       @type port: C{Port}
       @param callback: The callback function
       @type callback: C{callable}
    """
    self.__port = port  #: The port being configured
    self.__count = 0  #: The number of dependancies
    #: The callback vector
    self.__callback = callable(callback) and [callback] or []

  def add_callback(self, callback):
    """
       Add another callback for when this port and all its dependancies have
       been configured.

       @param callback: The callback function
       @type callback: C{callable}
    """
    self.__callback.append(callback)

  def config(self):
    """
       Configure the port and add all its dependancies onto the queue to be
       configured.
    """
    from pypkg.port import get
    assert self.__port.stage() < Port.CONFIG and self.__count == 0

    if self.__port.build_stage(Port.CONFIG, False):
      self.__count = len(self.__port.attr('depends')) + 1
      for i in self.__port.attr('depends'):
        port = get(i)
        if port.stage() < Port.CONFIG:
          config_builder(port, self.finish)
        else:
          self.finish()
    else:
      self.__count = 1
    self.finish()

  def finish(self):
    """
       Called when this port, or its dependancies, have been configured.  When
       all have been configured then call the callback (and remove ourselves
       from the configuration cache)
    """
    assert self.__count > 0
    self.__count -= 1
    if self.__count == 0:
      with self.lock:
        self.cache.pop(self.__port)
    else:
      return
    for i in self.__callback:
      i()

def config_builder(port, callback=None):
  """
     The builder for the config stage.  The port and all its dependancies are
     configured and then the callback function is called

     @param port: The port to configure
     @type port: C{port}
     @param callback: The callback function
     @type callback: C{callable}
  """
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

def index_builder():
  """
     Creates the INDEX of all the ports.
  """
  from logging import getLogger
  from os.path import join

  from pypkg.make import env, make_target, SUCCESS
  from pypkg.port import cache

  make = make_target('', ['-V', 'SUBDIR'], pipe=True)
  if make.wait() is not SUCCESS:
    getLogger('pypkg.builder.index').error("Unable to get global " \
              "directory list for ports at '%s'" % env['PORTSDIR'])
    return

  ports = []

  for i in make.stdout.read().split():
    smake = make_target(i, ['-V', 'SUBDIR'], pipe=True)
    if smake.wait() is not SUCCESS:
      getLogger('pypkg.builder.index').error("Unable to get subdirectory" \
      "list for ports under '%s'" % join(env['PORTSDIR'], i))
      continue
    
    for j in smake.stdout.read().split():
      port = join(i, j)
      ports.append(port)
      cache.add(port)
      
  index = open('/tmp/INDEX', 'w')
  for i in ports:
    try:
      index.write(cache[i].describe())
      index.write('\n')
    except KeyError:
      continue

  index.close()

#: The builder for the fetch stage
fetch_builder   = StageBuilder(Port.FETCH, fetch_queue)
#: The builder for the build stage
build_builder   = StageBuilder(Port.BUILD, build_queue, fetch_builder)
#: The builder for the install stage
install_builder = StageBuilder(Port.INSTALL, install_queue, build_builder)
