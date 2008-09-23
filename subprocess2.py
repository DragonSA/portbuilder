"""
The subprocess2 module.  This module is a derivative of subprocess.  It manages
a thread that handles all the creating requests of Popen.  This prevents some
locking contentions.
"""

from __future__ import with_statement

import subprocess

__all__ = subprocess.__all__ + ['PopenQueue']

class _PopenQueue(object):
  def __init__(self):
    from atexit import register
    from threading import Condition, Lock, Thread

    self._lock = Lock()
    self._signal_client = Condition(self._lock)
    self._signal_worker = Condition(self._lock)

    self._terminate = False
    self._job_cnt = 0
    self._queue = []
    self._popen = {}

    thread = Thread(target=self.worker)
    thread.setDaemon(True)
    thread.start()
    register(self.terminate)

  def job(self, jid):
    with self._lock:
      return jid in self._popen

  def terminate(self):
    with self._lock:
      self._terminate = True
      self._signal_worker.notify()
      self._signal_client.notifyAll()

  def put(self, *args, **kwargs):
    with self._lock:
      if self._terminate:
        return -1

      jid = self._job_cnt
      self._job_cnt += 1

      self._queue.append((jid, args, kwargs))
      self._signal_worker.notify()

    return jid

  def put_wait(self, *args, **kwargs):
    return self.wait(self.put(*args, **kwargs))

  def wait(self, jid):
    if jid < 0:
      return None

    with self._lock:
      while jid not in self._popen and not self._terminate:
        self._signal_client.wait()

      if jid in self._popen:
        return self._popen.pop(jid)

      return None

  def worker(self):
    while True:
      with self._lock:
        while len(self._queue) == 0 and not self._terminate:
          self._signal_worker.wait()

        if self._terminate:
          return

        jid, args, kwargs = self._queue.pop(0)

      self._popen[jid] = subprocess.Popen(close_fds=True, *args, **kwargs)

      with self._lock:
        self._signal_client.notifyAll()

PopenQueue = _PopenQueue()
Popen = PopenQueue.put_wait

# Make pylint happier:
PIPE = subprocess.PIPE
STDOUT = subprocess.STDOUT

for i in __all__:
  if i not in locals():
    locals()[i] = getattr(subprocess, i)
