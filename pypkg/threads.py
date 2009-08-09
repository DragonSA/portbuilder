"""
The threading module.  This module implements various locking diagnostics.
To use the locking diagnostics use the WatchLock or WatchRLock for the locks
that should be monitored for deadlocks.
"""
from __future__ import absolute_import, with_statement
from threading import Lock, RLock, Thread, current_thread, _RLock

__all__ = ['Lock', 'RLock', 'Thread', 'WatchLock', 'WatchRLock', 'current_thread']

class _Watcher(object):
  def __init__(self):
    self.__lock = Lock()
    self.__locks = {}
    self.__waiting = {}
    watcher = Thread(target=self._watcher)
    watcher.daemon = True
    watcher.start()

  def wait(self, lock):
    from traceback import extract_stack
    with self.__lock:
      self.__waiting[current_thread()] = (lock, extract_stack())

  def got(self):
    # Assert checked by wait(lock)
    with self.__lock:
      me = current_thread()
      lock, bt = self.__waiting[me]
      self.__waiting[me] = None
      self.__locks[lock] = (me, bt)

  def acquired(self, lock):
    from traceback import extract_stack
    with self.__lock:
      self.__locks[lock] = (current_thread(), extract_stack())

  def released(self, lock):
    with self.__lock:
      self.__locks.pop(lock)

  def _watcher(self):
    from time import sleep
    while True:
      sleep(5)
      with self.__lock:
        for lock, thr in [(i[1][0], i[0]) for i in self.__waiting.iteritems() if i[1]]:
          stack = [(lock, thr)]
          threads = [thr]
          while True:
            if self.__locks.has_key(lock):
              thr = self.__locks[lock][0]
              if self.__waiting.has_key(thr) and self.__waiting[thr]:
                lock = self.__waiting[thr][0]
                if thr == threads[0]:
                  self._report_cyclic(stack)
                elif thr not in threads:
                  stack.append((lock, thr))
                  threads.append(thr)
                  continue
            # If no next link
            break

  def _report_cyclic(self, stack):
    from os import getpid, kill
    from logging import getLogger
    from signal import SIGKILL
    from sys import stderr
    from time import sleep
    from traceback import format_list

    from .exit import terminate

    msg = " --- Cyclic deadlock ---\n"
    for lock, thr in stack:
      msg += 'Thread "%s" waiting for lock "%s"\n' % (thr.name, str(lock))
      msg += '\tLock "%s" held by thread "%s"\n' % (str(lock), self.__locks[lock][0].name)

    msg += "\n --- Waiting threads traceback ---\n"
    for lock, thr in stack:
      msg += 'Thread "%s" (waiting for lock "%s"):\n' % (thr.name, str(lock))
      msg += ''.join(format_list(self.__waiting[thr][1]))

    msg += "\n --- Acquired locks traceback ---\n"
    for i in stack:
      lock = i[0]
      msg += 'Lock "%s" (held by thread "%s"):\n' % (str(lock), self.__locks[lock][0].name)
      msg += ''.join(format_list(self.__locks[lock][1]))

    stderr.write("Cyclic deadlock detected, terminating problem\n")
    getLogger("pypkg.threading").critical(msg)
    terminate()
    sleep(5)
    kill(getpid(), SIGKILL)

_watcher = _Watcher()

def _acquire_wait(lock, timeout):
  from time import sleep, time
  # Balancing act:  We can't afford a pure busy loop, so we
  # have to sleep; but if we sleep the whole timeout time,
  # we'll be unresponsive.  The scheme here sleeps very
  # little at first, longer as time goes on, but never longer
  # than 20 times per second (or the timeout time remaining).
  endtime = time() + timeout
  delay = 0.0005 # 500 us -> initial delay of 1 ms
  while True:
    if lock.acquire(False):
      return True
    remaining = endtime - time()
    if remaining <= 0:
      return False
    delay = min(delay * 2, remaining, .05)
    sleep(delay)

class WatchLock(object):
  __lock_count = 0
  __intr_lock  = Lock()

  def __init__(self):
    self.__lock = Lock()
    with WatchLock.__intr_lock:
      self.__name = "WatchLock_%i" % WatchLock.__lock_count
      WatchLock.__lock_count += 1

  def __repr__(self):
    return "<%s(%s)>" % (self.__class__.__name__, repr(self.__lock))

  def __str__(self):
    return self.__name

  def acquire(self, blocking=True):
    if not blocking:
      status = self.__lock.acquire(wait)
      if status:
        _watcher.acquired(self)
      return status
    else:
      _watcher.wait(self)
      self.__lock.acquire()
      _watcher.got()
      return True

  __enter__ = acquire

  def release(self):
    self.__lock.release()
    _watcher.released(self)

  def __exit__(self, t, v, bt):
    self.release()

  def locked(self):
    return self.__lock.locked()

class WatchRLock(_RLock):
  __lock_count = 0
  __intr_lock  = Lock()

  def __init__(self):
    _RLock.__init__(self)
    self._RLock__block = WatchLock()
    with WatchRLock.__intr_lock:
      self.__name = "WatchRLock_%i" % WatchRLock.__lock_count
      WatchRLock.__lock_count += 1

  def __str__(self):
    return self.__name
