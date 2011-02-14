"""Manages jobs."""

__all__ = ["QueueManager"]

class QueueManager(object):
  """Manages jobs and runs them as resources come available."""

  def __init__(self, load=1):
    """Initialise the manager with an indication of load available."""
    self.load = load
    self.queue = []
    self.active = []
    self.stalled = []
    self.active_load = 0

  def add(self, job):
    """Add a job to be run."""
    assert(job not in self.queue)
    self.queue.append(job)
    self.queue.sort(key=lambda x: -x.priority)
    if self.active_load < self.load:
      self._run()

  def done(self, job):
    """Indicates a job has completed."""
    self.active.remove(job)
    self.active_load -= job.load
    if self.active_load < self.load:
      self._run()

  def remove(self, job):
    """Remove a job from being run."""
    try:
      self.queue.remove(job)
    except ValueError:
      return False
    return True

  def _run(self):
    """Fills up the remaining load with jobs"""
    from .job import StalledJob
    assert(self.active_load < self.load)

    stalled = []
    for queue in (self.stalled, self.queue):
      while self.active_load < self.load and len(queue):
        job = self._find_job(self.load - self.active_load, queue)
        try:
          self.active_load += job.load
          self.active.append(job)
          job.run(self)
        except StalledJob:
          self.active_load -= job.load
          self.active.remove(job)
          stalled.append(job)
    if len(stalled):
      self.stalled.extend(stalled)
      self.stalled.sort(key=lambda x: -x.priority)

  @staticmethod
  def _find_job(load, queue):
    """Find a job from queue that has at most load."""
    best_job = queue[0]
    best_idx = 0
    if best_job.load <= load:
      return queue.pop(0)
    for idx in range(1, len(queue)):
      job = queue[idx]
      if job.load <= load:
        return queue.pop(idx)
      if best_job.load > job.load:
        best_job = job
        best_idx = idx
    return queue.pop(best_idx)
