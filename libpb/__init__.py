"""FreeBSD port building infrastructure."""

from __future__ import absolute_import

from . import event

__all__ = ["event", "state", "stop"]


class StateTracker(object):
  """Track the state of the port builder."""

  class Stage(object):
    """Information about each stage of the build process."""

    def __init__(self, builder, next_stage=None):
      self.builder = builder
      self.stage = builder.stage
      self.active  = []
      self.queued  = []
      self.pending = []
      self.failed  = []
      self.done    = []
      self.status = (self.pending, self.queued, self.active, self.failed, (), self.done)

      self._ports = set()
      self._next_stage = next_stage

      builder.update.connect(self._update)

    def __getitem__(self, status):
      return self.status[status]

    def _update(self, _builder, status, port):
      from bisect import insort
      from .builder import Builder

      if status == Builder.ADDED:
        insort(self.pending, port)
        self._ports.add(port)
        if self._next_stage is not None:
          self._next_stage.previous_stage_started(port)
      elif status == Builder.QUEUED:
        self.pending.remove(port)
        insort(self.queued, port)
      elif status == Builder.ACTIVE:
        self.queued.remove(port)
        self.active.append(port)
      else:
        if port in self.active:
          self.active.remove(port)
        elif port in self.queued:
          self.queued.remove(port)
        else:
          self.pending.remove(port)
        self._ports.remove(port)
        if status == Builder.FAILED:
          if port.stage == self.stage:
            self.failed.append(port)
        elif status == Builder.DONE and port.stage == self.stage:
          self.done.append(port)
        if self._next_stage is not None:
          self._next_stage.previous_stage_finished(port)

    def cleanup(self):
      self.builder.update.disconnect(self._update)

    def previous_stage_started(self, port):
      if port in self._ports:
        self.pending.remove(port)

    def previous_stage_finished(self, port):
      if port in self._ports:
        from bisect import insort
        insort(self.pending, port)

  def __init__(self):
    from .builder import builders, depend_builder

    self.stages = [StateTracker.Stage(builders[-1])]
    for builder in reversed(builders[:-1]):
      self.stages.append(StateTracker.Stage(builder, self.stages[-1]))
    self.stages.reverse()

    self._resort = False
    depend_builder.update.connect(self._sort)

  def __del__(self):
    from .builder import depend_builder
    for i in self.stages:
      i.cleanup()
    depend_builder.update.disconnect(self._sort)

  def __getitem__(self, stage):
    return self.stages[stage - 1]

  def sort(self):
    if self._resort:
      for stage in self.stages:
        stage.pending.sort()
        stage.queued.sort()
      self._resort = False

  def _sort(self, _builder, status, _port):
    from .builder import Builder
    if status in (Builder.FAILED, Builder.SUCCEEDED, Builder.DONE):
      self._resort = True


def stop(kill=False, kill_clean=False):
  """Stop building ports and cleanup."""
  from os import kill, killpg
  from signal import SIGTERM, SIGKILL
  from .builder import builders
  from .env import cpus, flags
  from .queue import attr_queue, clean_queue, queues

  if flags["no_op"]:
    raise SystemExit(254)

  flags["mode"] = "clean"

  kill_queues = (attr_queue,) + queues
  if kill_clean:
    kill_queues += (clean_queue,)

  # Kill all active jobs
  for queue in kill_queues:
    for pid in (job.pid for job in queue.active if job.pid):
      try:
        if kill:
          killpg(pid, SIGKILL)
        else:
          kill(pid, SIGTERM)
      except OSError:
        pass

  # Stop all queues
  attr_queue.load = 0
  for queue in queues:
    queue.load = 0

  # Make cleaning go a bit faster
  if kill_clean:
    clean_queue.load = 0
    return
  else:
    clean_queue.load = cpus

  # Wait for all active ports to finish so that they may be cleaned
  active = set()
  for queue in queues:
    for job in queue.active:
      port = job.port
      active.add(port)
      port.stage_completed.connect(lambda x: x.clean())

  # Clean all other outstanding ports
  for builder in builders:
    for port in builder.ports:
      if port not in active:
        port.clean()

state = StateTracker()
