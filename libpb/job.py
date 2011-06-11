"""Job handling for queue managers."""

from __future__ import absolute_import

from abc import abstractmethod, ABCMeta
from .signal import Signal, SignalProperty

__all__ = ["Job", "PortJob", "StalledJob"]

class StalledJob(RuntimeError):
  """Exception indicating the job cannot run right now."""
  pass

class Job(Signal):
  """Handles queued jobs with callbacks, prioritising and load management."""

  __metaclass__ = ABCMeta

  started = SignalProperty("Job.started")

  def __init__(self, load=1, priority=0):
    """Initiate a job with a given priority and load.

    Higher the value of priority, the greater the precedent.  Load indicates
    how many resources is required to run the job (i.e. CPUs)."""
    Signal.__init__(self)
    if priority is not None:
      self.priority = priority
    self.load = load
    self.pid = None
    self.__manager = None

  def __lt__(self, other):
    return self.priority > other.priority

  def run(self, manager):
    """Run the job.

    The method may throw StalledJob, indicating the job should be placed on the
    stalled queue and another run in its place."""
    self.__manager = manager
    self.started.emit(self)
    self.work()

  def done(self):
    """Utility method to indicate the work has completed."""
    self.pid = None
    if self.__manager:
      self.__manager.done(self)
    self.emit(self)

  @abstractmethod
  def work(self):
    """Do the hard work.

    This method should be subclassed so as to do something useful."""
    pass

class AttrJob(Job):
  """A port attributes job."""

  def __init__(self, attr):
    Job.__init__(self)
    self.attr = attr

  def __repr__(self):
    return "<AttrJob(origin=%s)>" % self.attr.origin

  def work(self):
    """Fetch a ports attributes."""
    self.pid = self.attr.get().connect(self._done).pid

  def _done(self, _make):
    """Callback special function with origin and attributes."""
    self.done()

class CleanJob(Job):
  """Clean a port job."""

  def __init__(self, port):
    Job.__init__(self)
    self.port = port
    self.pid = None
    self.status = None

  def __repr__(self):
    return "<CleanJob(%s)>" % self.port

  def work(self):
    """Clean a port."""
    from .make import make_target
    make = make_target(self.port, "clean", NOCLEANDEPENDS=True).connect(self._cleaned)
    self.pid = make.pid

  def _cleaned(self, popen):
    """Mark job as finished."""
    from .make import SUCCESS
    self.status = popen.wait() == SUCCESS
    self.done()

class PortJob(Job):
  """A port stage job.  Runs a port stage."""

  def __init__(self, port, stage):
    from .port.port import Port

    Job.__init__(self, port.load if stage == Port.BUILD else 1, None)
    self.pid = None
    self.port = port
    self.stage = stage

  def __repr__(self):
    return "<PortJob(port=%s, stage=%i)>" % (self.port.origin, self.stage)

  @property
  def priority(self):
    """Priority of port.  Port's priority may change without notice."""
    return self.port.dependent.priority

  def work(self):
    """Run the required port stage."""
    from .port.port import Port

    self.port.stage_completed.connect(self.stage_done)
    try:
      if self.stage == Port.PKGINSTALL:
        status = self.port.pkginstall()
      else:
        status = self.port.build_stage(self.stage)
      assert status is not False
      if not isinstance(status, bool) and status is not None:
        self.pid = status.pid
    except StalledJob:
      self.port.stage_completed.disconnect(self.stage_done)
      raise

  def stage_done(self, port=None):
    """Handle the completion of a port stage."""
    if port is None:
      from .event import post_event
      post_event(self.done)
    elif port.stage >= self.stage:
      self.port.stage_completed.disconnect(self.stage_done)
      self.done()
