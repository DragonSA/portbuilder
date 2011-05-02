"""Monitor subprocesses for completion (via signal(3))"""

from __future__ import absolute_import

__all__ = ["active_popen", "add_popen", "children"]

class ChildrenMonitor(object):
  """Monitor subprocesses."""

  def __init__(self):
    """Initialise subprocess monitor."""
    self._pid_map = {}

  def __len__(self):
    """Number of active subprocesses."""
    return len(self._pid_map)

  def add_popen(self, popen, callback):
    """Add a popen instance to be monitored, with callback function."""
    from subprocess import Popen

    if isinstance(popen, Popen):
      from .event import event
      self._pid_map[popen.pid] = (popen, callback)
      event(popen, "p-").connect(self._process_signal)
    else:
      from .event import post_event
      post_event(callback, popen)

  def children(self):
    """Returns all the current children."""
    return self._pid_map.keys()

  def _process_signal(self, popen):
    """Update the subprocess object and dispatch the callback."""
    from .event import post_event, event

    popen, callback = self._pid_map.pop(popen.pid)

    post_event(callback, popen)

_monitor = ChildrenMonitor()

active_popen = _monitor.__len__
add_popen    = _monitor.add_popen
children     = _monitor.children
