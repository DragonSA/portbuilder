"""
The target module.  This module handles executing various stages for building
ports.
"""
from __future__ import absolute_import, with_statement

from .port import Dependancy, Dependant, Port
from .queue import config_queue, fetch_queue, build_queue, install_queue

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

  def __len__(self):
    """
       The number of callbacks required before actual call

       @return: Number of calls left
       @rtype: C{int}
    """
    return self.__count

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

def protected_callback(callback):
  """
     Call an object.  Prevent exceptions from propogating.

     @param callback: The object to call
     @type callback: C{callable}
     @return: The callback result, or None
  """
  try:
    if callable(callback):
      return callback()
  except KeyboardInterrupt:
    from .exit import terminate
    terminate()
  except BaseException:
    from logging import getLogger
    getLogger('pypkg.callback').exception("Callback object threw exception: " +
                                          str(callback))
  return None

class StageBuilder(object):
  """
     The StageBuilder class.  This class handles building a particular stage
  """

  ACTIVE  = 0
  QUEUED  = 1
  PENDING = 2
  FAILED  = 3

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
    self.__queues = ([], [], [], [])  #: The location of the queues
                                      # (active, queued, pending, failed)

  def put(self, port, callback=None):
    """
       Place a port on the queue to be build.  When the port has finished call
       the given callback.

       @param port: The port to build
       @type port: C{Port} or C{str}
       @param callback: The callback function
       @type callback: C{callable}
    """
    if port.stage() < Port.CONFIG and self.__stage != Port.CONFIG:
      config_builder(port, lambda: self.put(port, callback))
      return
    elif self.__stage != Port.CONFIG:
      # Make sure we have dependant object created
      port.dependancy()

    # Make sure the ports dependant handler has been created:
    with self.__lock:
      if self.__building.has_key(port):
        if callable(callback):
          self.__building[port].append(callback)
        return

      with port.lock():
        bail = self._port_check(port)
        if not bail:
          self.__building[port] = callable(callback) and [callback] or []
          self.__queues[StageBuilder.PENDING].append(port)

          depends = self._depends_check(port)
          prev_stage = stage < self.__stage - 1 or \
                      (port.working() and stage == self.__stage - 1)
          assert self.__prev_builder is not None or not prev_stage

    if bail:
      self.__log.debug("Port cannot be built: ``%s''" % port.origin())
      protected_callback(callback)
      return

    if not len(depends) and not prev_stage:
      self.queue(port)
      return

    callback = Caller(len(depends) + (prev_stage and 1 or 0),
                      lambda: self.queue(port))
    self.__log.debug("Placing port onto queue after %i call(s): ``%s''" %
                     (len(callback), port.origin()))

    for i in depends:
      install_builder(i, callback)

    if prev_stage:
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
      self.__queues[StageBuilder.QUEUED].remove(port)
      self.__queues[StageBuilder.ACTIVE].append(port)

    if not port.build_stage(self.__stage):
      with self.__lock:
        self.__queues[StageBuilder.FAILED].append(port)

    self.__callbacks(port)

  def queue(self, port):
    """
       Place a port on the queue (this is for delayed queueing).

       @param port: The port to place on the queue
       @type port: C{Port}
    """
    assert self.__building.has_key(port)

    if self._port_check(port):
      self.__log.debug("Port will not be built: ``%s''" % port.origin())
      self.__callbacks(port, 2)
    else:
      assert self.__stage == Port.CONFIG or port.dependancy().check(self.__stage)
      assert port.stage() == self.__stage - 1 and not port.working()

      with self.__lock:
        self.__queues[StageBuilder.PENDING].remove(port)
        self.__queues[StageBuilder.QUEUED].append(port)

      self.__log.debug("Placing port onto queue: ``%s''" % port.origin())
      self._put_queue(port)

  def has_port(self, port):
    """
       Indicates if we have the port to be built.

       @param port: The port
       @type port: C{Port}
       @return: If we have the port
       @rtype: C{bool}
    """
    return self.__building.has_key(port)

  def stats(self, summary=False):
    """
       The statistics about the ports in the queue.  If the ports are active
       (i.e. building), queued to be active or waiting for another port...

       @param summary: If only the lengths of the queues are required
       @type summary: C{bool}
       @return: The list of ports (active, queued, pending, failures)
       @rtype: C{([Port], [Port], [Port], [Port])}
    """
    from copy import copy
    with self.__lock:
      qcopy = ()
      for i in self.__queues:
        if summary:
          qcopy += (len(i),)
        else:
          qcopy += (copy(i),)
      return qcopy

  def stalled(self):
    """
       Indicates if a port has stalled.  Places the port back onto the queue and
       allows another port to work.
    """
    #jid = self.__queue.jid()
    #port =

    #with self.__lock:
    #  self.__queues[StageBuilder.ACTIVE].remove(port)
    #  self.__queues[StageBuilder.QUEUED].insert(0, port)

    self.__queue.stalled()

    #with self.__lock:
    #  self.__queues[StageBuilder.QUEUED].remove(port)
    #  self.__queues[StageBuilder.ACTIVE].append(port)

  def _port_check(self, port):
    """
       Checks if the port can be built at this stage.

       @param port: The port
       @type port: C{Port}
       @return: If the port can be built
       @rtype: C{bool}
    """
    return port.failed() or port.dependant().failed() or \
                                                   port.stage() >= self.__stage

  def _depends_check(self, port):
    """
       Checks which dependancies need to be resolved.

       @param port: The port
       @type port: C{Port}
       @return: The dependancies that need to be resolved
       @rtype: C{[Port]}
    """
    depends = []
    for i in port.dependancy().get(Dependancy.STAGE2DEPENDS[self.__stage]):
      if i.dependant().status() == Dependant.UNRESOLV:
        depends.append(i)
    return depends

  def _put_queue(self, port):
    """
       Place a port onto the queue

       @param port: The port to place on the queue
       @type port: C{Port}
    """
    self.__queue.put(lambda: self.build(port))

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
      protected_callback(i)

class ConfigBuilder(StageBuilder):
  """
     Configures a port.
  """

  def __init__(self):
    """
       Create a target builder for a given stage using a given queue.  Also, if
       a previous stage is handled by a builder then use that builder to for the
       previous stages.

       @param prev_builder: The builder for the previous stage
       @type prev_builder: C{callable}
    """
    from .queue import config_queue

    StageBuilder.__init__(self, Port.CONFIG, config_queue)

  def _depends_check(self, port):
    """
       Checks which dependancies need to be resolved.

       @param port: The port
       @type port: C{Port}
       @return: The dependancies that need to be resolved
       @rtype: C{[Port]}
    """
    return []

class BuildBuilder(StageBuilder):
  """
     Builds a port.
  """

  def __init__(self, prev_builder=None):
    """
       Create a target builder for a given stage using a given queue.  Also, if
       a previous stage is handled by a builder then use that builder to for the
       previous stages.

       @param prev_builder: The builder for the previous stage
       @type prev_builder: C{callable}
    """
    from .queue import build_queue

    StageBuilder.__init__(self, Port.BUILD, build_queue, prev_builder)

  def _put_queue(self, port):
    """
       Place a port onto the queue with the proper load.

       @param port: The port to place on the queue
       @type port: C{Port}
    """
    from .queue import build_queue, ncpu

    if port.attr('jobs_disable') or port.attr('jobs_unsafe'):
      load = 1
    elif port.attr('jobs_force') or port.attr('jobs_safe'):
      try:
        load = int(port.attr('jobs_number'))
      except ValueError:
        load = ncpu
    else:
      load = 1

    build_queue.put(lambda: self.build(port), load)

def fetchable(port):
  """
     Checks if a port is fetchable (hasn't failed or already been fetched).

     @param port: The port to check
     @type port: C{Port}
     @return: If the port is fetchable
     @rtype: C{bool}
  """
  return not port.failed() and (port.stage() < Port.FETCH or \
              (port.stage() == Port.FETCH and port.working()))

class RConfigBuilder(object):
  """
      Recursively place objects onto the queue.
  """

  def __init__(self, port, callback):
    """
        Initialise the internals and start the callback
    """
    from threading import RLock
    self.__lock = RLock()
    self.__pending = []
    self.__callback = callback

    self.put(port)

  def put(self, port):
    with self.__lock:
      if port not in self.__pending:
        if port.status() < Port.CONFIG:
          queue = [port]
        else:
          queue = []
          depends = port.dependancy().get()
          idx = 0
          while idx < len(depends):
            port = depends[idx]
            if port.status() < Port.CONFIG:
              if port not in self.__pending:
                queue.append(port)
            else:
              depends.extend([i for i in port.dependancy().get()
                              if i not in depends])
            idx += 1

        self.__pending.extend(queue)

        if not len(self.__pending):
          protected_callback(self.__callback)
        else:
          for i in queue:
            config_builder(port, lambda: self.configured(i))

  def configured(self, port):
    """
        A port has been configured, remove it from the pending.

        @param port: The port
        @type port: C{Port}
    """
    with self.__lock:
      self.__pending.remove(port)
      self.put(port)
rconfig_builder = RConfigBuilder

def rfetch_builder(self, port, callback=None, cache=None, lock=None):
  """
     Add a port to be recursively fetched.

     @param port: The port to recursively fetch
     @type port: C{Port}
     @param callback: The callback function to call once finished
     @type callback: C{Callable}
     @param cache: Cache of ports that been passed
     @type cache: C{[]}
     @param lock: Lock to access the cache
     @type lock: C{Lock}
  """
  if port.stage() < Port.CONFIG:
    config_builder(port, lambda: self.put(port, callback, cache, lock))
    return

  if cache is None or lock is None:
    from threading import Lock
    cache = []
    lock = Lock()

  fetch = fetchable(port)
  depends = port.dependancy().get()

  with lock:
    depends = [i for i in depends if i not in cache]
    if port not in cache:
      cache.append(port)
    cache.extend(depends)

  if not fetch and not len(depends):
    protected_callback(callback)
  else:
    callback = Caller(len(depends) + (fetch and 1 or 0), callback)

    for i in depends:
      rfetch_builder(i, callback, cache, lock)

    if fetch:
      fetch_builder(i, callback)

def index_builder():
  """
     Creates the INDEX of all the ports.
  """
  from logging import getLogger
  from os.path import join

  from .make import env, make_target, SUCCESS
  from .port import cache

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

#: The builder for the config stage
config_builder  = ConfigBuilder()
#: The builder for the fetch stage
fetch_builder   = StageBuilder(Port.FETCH, fetch_queue, config_queue)
#: The builder for the build stage
build_builder   = BuildBuilder(fetch_builder)
#: The builder for the install stage
install_builder = StageBuilder(Port.INSTALL, install_queue, build_builder)
