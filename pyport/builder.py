"""Stage building infrastructure."""

from .port.port import Port
from .queue import checksum_queue, fetch_queue, build_queue, install_queue

__all__ = ["config_builder", "checksum_builder", "fetch_builder",
           "build_builder", "install_builder"]

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

  def add(self, port, callback=None):
    """Add a port to be configured."""
    assert port.stage < port.CONFIG

    if port in self.ports:
      self.ports[port].connect(callback)
    else:
      from .job import PortJob
      from .queue import config_queue

      port.stage_completed.connect(self._refresh_queues)
      job = PortJob(port, port.CONFIG)
      job.connect(self._cleanup).connect(callback)
      self.ports[port] = job
      config_queue.add(job)

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

  def __init__(self, stage, queue, prev_builder=None):
    """Initialise port stage builder."""
    self.ports = {}
    self.failed = []
    self.cleanup = set()
    self._pending = {}
    self._depends = {}
    self.stage = stage
    self.queue = queue
    self.prev_builder = prev_builder

  def __call__(self, port, callback=None):
    """Build the given port to the required stage."""
    self.cleanup.add(port)
    self.add(port, callback)

  def __repr__(self):
    return "<StageBuilder(%i)>" % self.stage

  def add(self, port, callback):
    """Add a port to be build for this stage."""
    assert not port.failed

    if port in self.ports:
      self.ports[port].connect(callback)
      return
    else:
      from .job import PortJob

      job = PortJob(port, self.stage)
      job.connect(self._cleanup).connect(callback)
      self.ports[port] = job

    if port.stage < port.CONFIG:
      config_builder.add(port, self._add)
    else:
      self._add(job)

  def _add(self, job):
    """Add a ports dependancies and prior stage to be built."""
    from .env import flags

    port = job.port

    if port.failed or port.dependancy.failed:
      self.ports[port].stage_done()
      return

    depends = port.dependancy.check(self.stage)

    self._pending[port] = len(depends)
    for p in depends:
      if p not in self._depends:
        self._depends[p] = set()
        install_builder(p, self._depend_resolv)
      self._depends[p].add(port)

    if not (flags["mode"] == "upgrade" and port.install_status >= port.CURRENT):
      if port.stage < self.stage - 1:
        self._pending[port] += 1
        self.prev_builder.add(port, self._stage_resolv)

    if not self._pending[port]:
      self._port_ready(port)

  def _cleanup(self, job):
    """Cleanup after the port has completed its stage."""
    del self.ports[job.port]
    self._port_failed(job.port)
    if job.port in self.cleanup:
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
    if port in self.failed:
      return True
    elif port.failed or port.dependancy.failed:
      from .event import post_event

      if port in self._depends:
        for deps in self._depends.pop(port):
          if deps not in self.prev_builder.ports and deps not in self.failed:
            post_event(self._port_failed, deps)
      if port not in self.prev_builder.ports:
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
      self.ports[port].stage_done()
    elif port.dependant.status == port.dependant.RESOLV:
      self.ports[port].stage_done()
    elif flags["mode"] == "upgrade" and port.install_status >= port.CURRENT:
      port.dependant.status_changed()
      self.ports[port].stage_done()
    else:
      assert port.stage >= self.stage - 1
      if port.stage < self.stage:
        self.queue.add(self.ports[port])
      else:
        self.ports[port].stage_done()

config_builder   = ConfigBuilder()
checksum_builder = StageBuilder(Port.CHECKSUM, checksum_queue, config_builder)
fetch_builder    = StageBuilder(Port.FETCH,    fetch_queue,    checksum_builder)
build_builder    = StageBuilder(Port.BUILD,    build_queue,    fetch_builder)
install_builder  = StageBuilder(Port.INSTALL,  install_queue,  build_builder)
