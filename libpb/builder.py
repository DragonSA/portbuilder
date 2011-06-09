"""Stage building infrastructure."""

from __future__ import absolute_import

from abc import ABCMeta, abstractmethod
from .port.port import Port
from .signal import SignalProperty

__all__ = ["Builder", "builders", "config_builder", "checksum_builder",
           "fetch_builder", "build_builder", "install_builder",
           "package_builder", "pkginstall_builder"]

class DependLoader(object):
  """Resolve a port as a dependency."""

  def __init__(self):
    self.ports = {}
    self.method = {}

  def __call__(self, port):
    """Try resolve a port as a dependency."""
    assert not port.failed

    if port not in self.ports:
      from .env import flags
      from .signal import Signal

      self.ports[port] = Signal()
      self.method[port] = flags["depend"][0]

      for builder in (install_builder, pkginstall_builder):
        if port in builder.ports:
          builder.add(port).connect(self._clean)
          self.method[port] = None
          break
      else:
        if not self._find_method(port):
          from .event import post_event

          signal = self.ports.pop(port)
          post_event(signal.emit, port)
          return signal
    return self.ports[port]

  def _clean(self, job):
    """Cleanup after a port has finished."""
    if job.port.failed and self.method[job.port]:
      # If the port failed and there is another method to try
      if self._find_method(job.port):
        return

    self.ports.pop(job.port).emit(job.port)

  def _find_method(self, port):
    """Find a method to resolve the port."""
    while True:
      method = self.method[port]
      self.method[port] = self._next(self.method[port])
      port.dependant.propogate = not self.method[port]
      if method is None:
        # No method left, port failed to resolve
        del self.method[port]
        port.failed = True
        port.dependant.status_changed()
        return False
      if self._resolve(port, method):
        return True

  def _resolve(self, port, method):
    """Try resolve the port using various methods."""
    from .env import flags

    if port.stage > Port.DEPEND:
      port.reset()
    if method == "build":
      if flags["package"]:
        # Connect to install job and give package_builder ownership (cleanup)
        job = install_builder.add(port)
        package_builder(port)
      else:
        job = install_builder(port)
    elif method == "package":
      from os.path import isfile

      if not isfile(flags["chroot"] + port.attr["pkgfile"]):
        return False
      job = pkginstall_builder(port)
    else:
      assert not "Unknown port resolve method"
    job.connect(self._clean)
    return True

  @staticmethod
  def _next(method):
    """Find the next method used to resolve a dependency."""
    from .env import flags

    try:
      return flags["depend"][flags["depend"].index(method) + 1]
    except IndexError:
      return None


class Builder(object):
  """Common code from building stages."""

  __metaclass__ = ABCMeta

  ADDED     = 0
  QUEUED    = 1
  ACTIVE    = 2
  FAILED    = 3
  SUCCEEDED = 4
  DONE      = 5

  update = SignalProperty("Builder.update")

  def __init__(self, stage, queue=None):
    """Initialise the builder."""
    self.queue = queue
    self.stage = stage
    self.failed = []
    self.ports = {}
    self.succeeded = []

  @abstractmethod
  def __call__(self, port):
    """Add port to this builder, where this builder is the primary builder for
    the port."""
    return self.add(port)

  @abstractmethod
  def add(self, port):
    """Add port to this builder."""
    pass


class ConfigBuilder(Builder):
  """Configure ports."""

  def __init__(self):
    """Initialise config builder."""
    from .queue import config_queue
    Builder.__init__(self, Port.CONFIG, config_queue)

  def __call__(self, port):
    """Configure the given port."""
    return self.add(port)

  def __repr__(self):
    return "<ConfigBuilder()>"

  def add(self, port):
    """Add a port to be configured."""
    assert port.stage < port.CONFIG

    if port in self.ports:
      return self.ports[port]
    else:
      from .job import PortJob

      # Create a config stage job and add it to the queue
      job = PortJob(port, port.CONFIG)
      job.connect(self._cleanup)
      self.ports[port] = job
      self.signal.emit(self, Builder.ADDED, port)
      self.queue.add(job)
      self.signal.emit(self, Builder.QUEUED, port)
      return job

  def _cleanup(self, job):
    """Cleanup after the port was configured."""
    if job.port.failed:
      self.failed.append(job.port)
      self.signal.emit(self, Builder.FAILED, port)
    else:
      self.signal.emit(self, Builder.SUCCEEDED, port)
    del self.ports[job.port]

class DependBuilder(Builder):
  """Load port's dependancies."""

  def __init__(self):
    """Initialise depend builder"""
    Builder.__init__(self, Port.DEPEND)

  def __call__(self, port):
    """Add a port to have its dependancies loaded."""
    return self.add(port)

  def __repr__(self):
    return "<DependBuilder()>"

  def add(self, port):
    """Add a port to have its dependancies loaded."""

    if port in self.ports:
      return self.ports[port]
    else:
      from .signal import Signal

      sig = Signal()
      self.ports[port] = sig
      self.update.emit(self, Builder.ADDED, port)
      if port.stage < Port.CONFIG:
        config_builder.add(port).connect(self._add)
      else:
        self.update.emit(self, Builder.QUEUED, port)
        self.update.emit(self, Builder.ACTIVE, port)
        port.stage_completed.connect(self._loaded)
        port.build_stage(Port.DEPEND)
      return sig

  def _add(self, job):
    """Load a ports dependencies."""
    port = job.port
    self.update.emit(self, Builder.QUEUED, port)
    self.update.emit(self, Builder.ACTIVE, port)
    port.stage_completed.connect(self._loaded)
    port.build_stage(Port.DEPEND)

  def _loaded(self, port):
    """Port has finished loading dependency."""
    from .queue import queues

    port.stage_completed.disconnect(self._loaded)
    if port.dependancy is not None:
      for queue in queues:
        queue.reorder()
    if port.failed:
      self.failed.append(port)
      self.update.emit(self, Builder.FAILED, port)
    else:
      self.update.emit(self, Builder.SUCCEEDED, port)
    self.ports.pop(port).emit(port)

class StageBuilder(Builder):
  """General port stage builder."""

  def __init__(self, stage, prev_builder=None):
    """Initialise port stage builder."""
    from .queue import queues

    Builder.__init__(self, stage, queues[stage - 2])

    self.cleanup = set()
    self._pending = {}
    self._depends = {}
    self.prev_builder = prev_builder

  def __call__(self, port):
    """Build the given port to the required stage."""
    self.cleanup.add(port)
    return self.add(port)

  def __repr__(self):
    return "<StageBuilder(%i)>" % self.stage

  def add(self, port):
    """Add a port to be build for this stage."""
    assert not port.failed

    if port in self.ports:
      return self.ports[port]
    else:
      from .job import PortJob

      # Create stage job
      job = PortJob(port, self.stage)
      job.connect(self._cleanup)
      self.ports[port] = job
      self.update.emit(self, Builder.ADDED, port)

      # Configure port then process it
      if port.stage < port.DEPEND:
        depend_builder.add(port).connect(self._add)
      else:
        self._add(port)
      return job

  def _add(self, port):
    """Add a ports dependancies and prior stage to be built."""
    from .env import flags

    # Don't try and build a port that has already failed (or cannot be built)
    if port.failed or port.dependancy.failed:
      self.ports[port].stage_done()
      return

    depends = port.dependancy.check(self.stage)

    # Add all outstanding ports to be installed
    self._pending[port] = len(depends)
    for p in depends:
      if p not in self._depends:
        self._depends[p] = set()
        depend(p).connect(self._depend_resolv)
      self._depends[p].add(port)

    # Build the previous stage if needed
    if self.prev_builder and (port.install_status <= flags["stage"] or port.force) and port.stage < self.stage - 1:
      self._pending[port] += 1
      self.prev_builder.add(port).connect(self._stage_resolv)
    elif self.stage == Port.PKGINSTALL:
      # Set port stage to prevent other builders from attempting to build and
      # so that monitor shows the correct stage of these ports
      port.stage = Port.PKGINSTALL - 1

    # Build stage if port is ready
    if not self._pending[port]:
      self._port_ready(port)

  def _started(self, job):
    job.started.disconnect(self._started)
    self.update.emit(self, Builder.ACTIVE, job.port)

  def _cleanup(self, job):
    """Cleanup after the port has completed its stage."""
    from .env import flags

    del self.ports[job.port]
    self._port_failed(job.port)
    if job.port in self.cleanup and not flags["mode"] == "clean":
      self.cleanup.remove(job.port)
      if not job.port.failed:
        self.succeeded.append(job.port)
        self.update.emit(self, Builder.DONE, job.port)
      job.port.clean()
    elif not job.port.failed:
      self.update.emit(self, Builder.SUCCEEDED, job.port)

  def _depend_resolv(self, port):
    """Update dependancy structures for resolved dependancy."""
    if not self._port_failed(port):
      for port in self._depends.pop(port):
        if port not in self.failed:
          self._pending[port] -= 1
          if not self._pending[port]:
            self._port_ready(port)

  def _stage_resolv(self, job):
    """Update pending structures for resolved prior stage."""
    if not self._port_failed(job.port):
      self._pending[job.port] -= 1
      if not self._pending[job.port]:
        self._port_ready(job.port)

  def _port_failed(self, port):
    """Handle a failing port."""
    from .env import flags

    if port in self.failed or flags["mode"] == "clean":
      return True
    elif port.failed or port.dependancy.failed:
      from .event import post_event

      if port in self._depends:
        # Inform all dependants that they have failed (because of us)
        for deps in self._depends.pop(port):
          if (not self.prev_builder or deps not in self.prev_builder.ports) and deps not in self.failed:
            post_event(self._port_failed, deps)
      if not self.prev_builder or port not in self.prev_builder.ports:
        # We only fail on at this stage if previous stage knowns about failure
        self.failed.append(port)
        self.update.emit(self, Builder.FAILED, port)
        if port in self.ports:
          del self._pending[port]
          self.ports[port].stage_done()
      return True
    return False

  def _port_ready(self, port):
    """Add a port to the stage queue."""
    from .env import flags

    del self._pending[port]
    if port.failed or port.dependancy.failed or port.dependancy.check(self.stage):
      # port cannot build
      self.ports[port].stage_done()
    elif self.stage == port.PACKAGE:
      # Checks specific for package building
      if port.stage < port.INSTALL:
        self.ports[port].stage_done()
      else:
        assert(port.stage == port.INSTALL)
        self._build_port(port)
    else:
      # Checks for self.stage <= port.INSTALL || self.stage == port.PKGINSTALL
      if port.dependant.status == port.dependant.RESOLV:
        # port does not need to build
        self.ports[port].stage_done()
      elif port.install_status > flags["stage"] and not port.force:
        # port already up to date, does not need to build
        port.dependant.status_changed()
        self.ports[port].stage_done()
      else:
        self._build_port(port)

  def _build_port(self, port):
    """Actually build the port."""
    assert port.stage >= self.stage - 1 or self.stage == port.PKGINSTALL
    if port.stage < self.stage:
      self.update.emit(self, Builder.QUEUED, port)
      self.ports[port].started.connect(self._started)
      self.queue.add(self.ports[port])
    else:
      self.ports[port].stage_done()

depend = DependLoader()
config_builder     = ConfigBuilder()
depend_builder     = DependBuilder()
checksum_builder   = StageBuilder(Port.CHECKSUM)
fetch_builder      = StageBuilder(Port.FETCH,   checksum_builder)
build_builder      = StageBuilder(Port.BUILD,   fetch_builder)
install_builder    = StageBuilder(Port.INSTALL, build_builder)
package_builder    = StageBuilder(Port.PACKAGE, install_builder)
pkginstall_builder = StageBuilder(Port.PKGINSTALL)
builders = (config_builder, depend_builder, checksum_builder, fetch_builder, build_builder, install_builder, package_builder, pkginstall_builder)
