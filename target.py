"""
The target module.  This module handles executing various stages for building
ports.  
"""
from __future__ import with_statement

from port import DependHandler, Port
from queue import config_queue, fetch_queue, build_queue, install_queue

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
    #: Logger for this Builder
    self.__lock = Lock()  #: Synchroniser lock for this builder
    #: Logger for this builder
    self.__log = getLogger("pypkg.builder." + Port.STAGE_NAME[stage])
    self.__stage = stage  #: The stage we are taking care of
    self.__queue = queue  #: The queue for this stage
    self.__prev_builder = prev_builder  #: The builder for the previous stage

    self.__building = {}  #: List of ports we are working on

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
      from port import port_cache
      port = port_cache.get(port)
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
      depends = port.depends()
      if stage < self.__stage - 1 or \
           (port.working() and stage == self.__stage - 1):
        assert self.__prev_builder is not None
        resolv_depends = False
      elif depends.check(self.__stage) > DependHandler.UNRESOLV:
        port_lock.release()
        self.queue(port)
        return
      else:
        if port.working():
          # TODO, port building outsite StageBuilder infrastructure!!!
          pass
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
    port.build_stage(self.__stage, False)
    with self.__lock:
      callbacks = self.__building.pop(port)
    for i in callbacks:
      i()

  def queue(self, port):
    """
       Place a port on the queue, this is for delayed queueing.

       @param port: The port to place on the queue
       @type port: C{Port}
    """
    assert self.__building.has_key(port)
    if not port.failed():
      # TODO: Assumptions may not be corrent, if a dependancy fails
      assert port.depends().check(self.__stage) > DependHandler.UNRESOLV
      assert port.stage() == self.__stage - 1 and not port.working()
      self.__queue.put(lambda: self.build(port))
    else:
      self.build(port)

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
    from port import port_cache
    assert self.__port.stage() < Port.CONFIG and self.__count == 0

    if self.__port.build_stage(Port.CONFIG, False):
      self.__count = len(self.__port.attr('depends')) + 1
      for i in self.__port.attr('depends'):
        port = port_cache[i]
        if port.stage() < Port.CONFIG:
          config_builder(port, self.finish)
        else:
          self.finish()
    self.finish()

  def finish(self):
    """
       Called when this port, or its dependancies, have been configured.  When
       all have been configured then call the callback (and remove ourselves
       from the configuration cache)
    """
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

def build_index():
  """
     Creates the INDEX of all the ports.
  """
  from make import make_target, SUCCESS
  from os.path import join
  from port import port_cache

  subdir = ['-V', 'SUBDIR']

  make = make_target('', subdir, pipe=True)
  if make.wait() is not SUCCESS:
    # TODO
    return

  ports = []
  for i in make.stdout.read().split():
    smake = make_target(i, subdir, pipe=True)
    if smake.wait() is not SUCCESS:
      # TODO
      print "Failed to get subdirs for", i
      continue
    for j in smake.stdout.read().split():
      port = join(i, j)
      ports.append(port)
      port_cache.add(port)

  port_map = {}
  for i in ports:
    port = port_cache.get(i)
    if port:
      port_map[port.attr['pkgname']] = port

  names = port_map.keys()
  names.sort()
  index = open('/tmp/INDEX')
  for i in names:
    # TODO
    index.write(i.describe())

#class FetchBuilder(StageBuilder):
  #"""
     #The FetchBuilder class.  This class is the same as StageBuilder except it
     #add the ability to do a recursive fetch of all dependancies of the current
     #port.  Whereas one would have to be installing ports to get similar
     #behaviour otherwise.  
  #"""
  #def __call__(self, port, callback=None, recurse=False):
    #"""
      #The builder for the fetch stage.  This is a wrapper around the
      #TargetBuilder for the fetch stage.  This wrapper adds the ability to
      #recursively fetch all dependancies' distfiles

      #@param port: The port to fetch
      #@type port: C{Port}
      #@param callback: The callback function
      #@type callback: C{callable}
      #@param recurse: Indicate if all dependancies need to be fetched
      #@type recurse: C{bool}
    #"""
    #from tools import recurse_depends

    #if recurse:
      #if port.stage() < Port.CONFIG:
        #config_builder(port, lambda: fetch_builder(port, callback, True))
        #return

      #depends = recurse_depends(port)

      #if callable(callback):
        #callback = Caller(len(depends) + 1, callback)
      #for i in depends:
        #self.put(i.port(), callback)
    #self.put(port, callback)

#: The builder for the fetch stage
fetch_builder   = StageBuilder(Port.FETCH, fetch_queue)
#: The builder for the build stage
build_builder   = StageBuilder(Port.BUILD, build_queue, fetch_builder)
#: The builder for the install stage
install_builder = StageBuilder(Port.INSTALL, install_queue, build_builder)
