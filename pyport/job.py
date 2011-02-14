"""Job handling for queue managers."""

from abc import abstractmethod, ABCMeta
from .signal import Signal

__all__ = ["Job", "PortJob", "StalledJob"]

class StalledJob(RuntimeError):
  """Exception indicating the job cannot run right now."""
  pass

class Job(Signal):
  """Handles queued jobs with callbacks, prioritising and load management."""

  __metaclass__ = ABCMeta

  def __init__(self, load=1, priority=0):
    """Initiate a job with a given priority and load.

    Higher the value of priority, the greater the precident.  Load indicates
    how many resources is required to run the job (i.e. CPUs)."""
    Signal.__init__(self)
    if not hasattr(self, "priority"):
      self.priority = priority
    self.load = load
    self.__manager = None

  def run(self, manager):
    """Run the job.

    The method may throw StalledJob, indicating the job should be placed on the
    stalled queue and another run in its place."""
    self.__manager = manager
    try:
      self.work()
    except StalledJob:
      self.__manager.stalled_job(self)

  def _done(self):
    """Utility method to indicate the work has completed."""
    self.__manager.done(self)
    self(self)

  @abstractmethod
  def work(self):
    """Do the hard work.

    This method should be subclassed so as to do something useful."""
    pass

class PortJob(Job):
  """A port stage job.  Runs a port stage."""

  def __init__(self, port, stage):
    # TODO
    Job.__init__(self, port.load)
    self.port = port
    self.stage = stage
    self.port.stage_completed.connect(self._stage_done)

  @property
  def priority(self):
    """Priority of port.  Port's priority may change without notice."""
    # TODO
    return self.port.priority

  def work(self):
    """Run the required port stage."""
    if not self.port.build_stage(self.stage):
      self._stage_done(self.port)

  def _stage_done(self, port):
    """Handle the completion of a port stage."""
    if port.stage >= self.stage:
      self._done()
      self.port.stage_completed.disconnect(self._stage_done)
