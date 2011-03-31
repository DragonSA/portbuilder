"""Stage building infrastructure."""

from __future__ import absolute_import

from .port.port import Port

__all__ = ["builders", "config_builder", "checksum_builder", "fetch_builder",
           "build_builder", "install_builder", "package_builder"]

class ConfigBuilder(object):
  """Configure ports."""

  def __init__(self):
    """Initialise config builder."""
    self.ports = {}
    self.failed = []

  def __call__(self, port):
    """Configure the given port."""
    self.add(port)

  def __repr__(self):
    return "<ConfigBuilder()>"

  def add(self, port):
    """Add a port to be configured."""
    assert port.stage < port.CONFIG

    if port in self.ports:
      return self.ports[port]
    else:
      from .job import PortJob
      from .queue import config_queue

      # Create a config stage job and add it to the queue
      port.stage_completed.connect(self._refresh_queues)
      job = PortJob(port, port.CONFIG)
      job.connect(self._cleanup)
      self.ports[port] = job
      config_queue.add(job)
      return job

  def _cleanup(self, job):
    """Cleanup after the port was configured."""
    if job.port.failed:
      self.failed.append(job.port)
    del self.ports[job.port]

  def _refresh_queues(self, port):
    """Inform all queues that priorities may have changed."""
    from .queue import queues

    port.stage_completed.disconnect(self._refresh_queues)
    if port.dependancy is not None:
      for queue in queues:
        queue.reorder()

class StageBuilder(object):
  """General port stage builder."""

  def __init__(self, stage, prev_builder=None):
    """Initialise port stage builder."""
    from .queue import queues

    self.ports = {}
    self.failed = []
    self.cleanup = set()
    self._pending = {}
    self._depends = {}
    self.stage = stage
    self.queue = queues[stage - 1]
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

      # Configure port then process it
      if port.stage < port.CONFIG:
        config_builder.add(port).connect(self._add)
      else:
        self._add(job)
      return job

  def _add(self, job):
    """Add a ports dependancies and prior stage to be built."""
    from .env import flags

    port = job.port

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
        if flags["package"]:
          # Connect to install job and give package_builder ownership (cleanup)
          install_builder.add(p).connect(self._depend_resolv)
          package_builder(p)
        else:
          install_builder(p).connect(self._depend_resolv)
      self._depends[p].add(port)

    # Build the previous stage if needed
    if (port.install_status <= flags["stage"] or port.force) and port.stage < self.stage - 1:
      self._pending[port] += 1
      self.prev_builder.add(port).connect(self._stage_resolv)

    # Build stage if port is ready
    if not self._pending[port]:
      self._port_ready(port)

  def _cleanup(self, job):
    """Cleanup after the port has completed its stage."""
    from .env import flags

    del self.ports[job.port]
    self._port_failed(job.port)
    if job.port in self.cleanup and not flags["mode"] == "clean":
      self.cleanup.remove(job.port)
      job.port.clean()

  def _depend_resolv(self, job):
    """Update dependancy structures for resolved dependancy."""
    if not self._port_failed(job.port):
      for port in self._depends.pop(job.port):
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
          if deps not in self.prev_builder.ports and deps not in self.failed:
            post_event(self._port_failed, deps)
      if port not in self.prev_builder.ports:
        # We only fail on at this stage if previous stage knowns about failure
        self.failed.append(port)
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
      # Checks for self.stage <= port.INSTALL
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
    assert port.stage >= self.stage - 1
    if port.stage < self.stage:
      self.queue.add(self.ports[port])
    else:
      self.ports[port].stage_done()

config_builder   = ConfigBuilder()
checksum_builder = StageBuilder(Port.CHECKSUM, config_builder)
fetch_builder    = StageBuilder(Port.FETCH,    checksum_builder)
build_builder    = StageBuilder(Port.BUILD,    fetch_builder)
install_builder  = StageBuilder(Port.INSTALL,  build_builder)
package_builder  = StageBuilder(Port.PACKAGE,  install_builder)
builders = (config_builder, checksum_builder, fetch_builder, build_builder, install_builder, package_builder)
