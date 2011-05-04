"""FreeBSD port building infrastructure."""

from __future__ import absolute_import

from . import event

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
