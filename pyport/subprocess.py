"""Monitor subprocesses for completion (via signal(3))"""

from __future__ import absolute_import

__all__ = ["active_popen", "add_popen"]

class ChildrenMonitor(object):
  """Monitor subprocesses."""

  def __init__(self):
    """Initialise subprocess monitor."""
    from signal import signal, SIGCHLD

    self._pid_map = {}
    signal(SIGCHLD, self._signal)

  def __len__(self):
    """Number of active subprocesses."""
    return len(self._pid_map)

  def add_popen(self, popen, callback):
    """Add a popen instance to be monitored, with callback function."""
    self._pid_map[popen.pid] = (popen, callback)

  def _signal(self, _signum, _frame):
    """Handle a signal from child process."""
    from os import waitpid, WNOHANG
    from .event import post_event

    try:
      while True:
        pid, status = waitpid(-1, WNOHANG)
        if not pid:
          break

        if status & 0xff:
          # If low byte set then process exited due to signal
          status = -(status & 0xff)
        else:
          # Else high byte contains exit status
          status = status >> 8
        post_event(self._process_signal, pid, status)
    except OSError:
      pass

  def _process_signal(self, pid, status):
    """Update the subprocess object and dispatch the callback."""
    from .event import post_event

    popen, callback = self._pid_map.pop(pid)
    popen.returncode = status

    post_event(callback, popen)

_monitor = ChildrenMonitor()

active_popen = _monitor.__len__
add_popen = _monitor.add_popen
