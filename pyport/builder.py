"""Stage building infrastructure."""

from .port.port import Port
from . import checksum_queue, fetch_queue, build_queue, install_queue

__all__ = ["config_builder", "checksum_builder", "fetch_builder",
           "build_builder", "install_builder"]

class ConfigBuilder(object):
  """Configure ports."""

  def __init__(self):
    """Initialise config builder."""
    self.ports = {}

  def add(self, port, callback=None):
    """Add a port to be configured."""
    assert port.stage < port.CONFIG

    if port in self.ports:
      return self.ports[port].connect(callback)
    else:
      from .job import PortJob
      from . import config_queue

      job = PortJob(port, port.CONFIG)
      job.connect(self._cleanup).connect(callback)
      self.ports[port] = job
      config_queue.add(job)
      return job

  def _cleanup(self, job):
    """Cleanup after the port was configured."""
    del self.ports[job.port]

class StageBuilder(object):
  """General port stage builder."""

  def __init__(self, stage, queue, prev_builder=None):
    """Initialise port stage builder."""
    self.ports = {}
    self._pending = {}
    self._depends = {}
    self.stage = stage
    self.queue = queue
    self.prev_builder = prev_builder

  def add(self, port, callback=None):
    """Add a port to be build for this stage."""
    assert not  port.failed

    if port in self.ports:
      return self.ports[port].connect(callback)
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
    port = job.port

    if port.failed or port.dependancy.failed:
      self.ports[port].stage_done()

    depends = port.dependancy.check(self.stage)
    if not depends and port.stage == self.stage - 1:
      self.queue.add(self.ports[port])
      return

    self._pending[port] = len(depends)
    for p in depends:
      if p not in self._depends:
        self._depends[p] = set()
      self._depends[p].add(port)
      install_builder.add(p, self._depend_resolv)

    if port.stage < self.stage - 1:
      self._pending[port] += 1
      self.prev_builder.add(port, self._stage_resolv)

  def _cleanup(self, job):
    """Cleanup after the port has completed its stage."""
    del self.ports[job.port]

  def _depend_resolv(self, job):
    """Update dependancy structures for resolved dependancy."""
    for port in self._depends[job.port]:
      self._pending[port] -= 1
      if not self._pending[port]:
        self._port_ready(port)
    del self._depends[job.port]

  def _stage_resolv(self, job):
    """Update pending structures for resolved prior stage."""
    if job.port.stage >= self.stage:
      # something
      pass
    self._pending[job.port] -= 1
    if not self._pending[job.port]:
      self._port_ready(job.port)

  def _port_ready(self, port):
    """Add a port to the stage queue."""
    if port.failed or port.dependancy.check(self.stage):
      self.ports[port].stage_done()
    else:
      self.queue.add(self.ports[port])
      del self._pending[port]

config_builder   = ConfigBuilder()
checksum_builder = StageBuilder(Port.CHECKSUM, checksum_queue)
fetch_builder    = StageBuilder(Port.FETCH,    fetch_queue,   checksum_builder)
build_builder    = StageBuilder(Port.BUILD,    build_queue,   fetch_builder)
install_builder  = StageBuilder(Port.INSTALL,  install_queue, build_builder)
