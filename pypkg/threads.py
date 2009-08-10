"""
The threading module.  This module implements various locking diagnostics.
To use the locking diagnostics use the WatchLock or WatchRLock for the locks
that should be monitored for deadlocks.
"""
from __future__ import absolute_import, with_statement
import threading
from thread import allocate_lock as _allocate_lock
from threading import *
from threading import _active, _DummyThread

__all__ = threading.__all__ + ['WatchLock', 'WatchRLock']

class _Watcher(object):
  def __init__(self):
    self.__lock = _allocate_lock()
    self.__locks = {}
    self.__waiting = {}
    watcher = threading.Thread(target=self._watcher)
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

  def release(self, lock, release):
    assert lock.locked()
    with self.__lock:
      release()
      self.__locks.pop(lock)
  
  def info(self, stack=None):
    from traceback import format_list
    if not stack:
      all_acq = True
      stack = [(i[1][0], i[0]) for i in self.__waiting.iteritems() if i[1]]
      msg = " --- Waiting threads ---\n"
    else:
      all_acq = False
      msg = " --- Cyclic deadlock ---\n"
    for lock, thr in stack:
      msg += 'Thread "%s" waiting for lock "%s"\n' % (thr.name, str(lock))
      msg += '\tLock "%s" held by thread "%s"\n' % (str(lock), self.__locks[lock][0].name)

    msg += "\n\n --- Waiting threads traceback ---\n"
    for lock, thr in stack:
      msg += '\nThread "%s" (waiting for lock "%s"):\n' % (thr.name, str(lock))
      msg += ''.join(format_list(self.__waiting[thr][1]))

    if all_acq:
      stack = [(i[0], i[1][0]) for i in self.__locks.iteritems()]
    msg += "\n\n --- Acquired locks traceback ---\n"
    for i in stack:
      lock = i[0]
      msg += '\nLock "%s" (held by thread "%s"):\n' % (str(lock), self.__locks[lock][0].name)
      msg += ''.join(format_list(self.__locks[lock][1]))
    return msg

  def _watcher(self):
    from time import sleep
    from sys import stderr
    while True:
      sleep(5)
      #stderr.write(self.info())
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

    from .exit import terminate

    stderr.write("Cyclic deadlock detected, terminating program\n")
    getLogger("pypkg.threading").critical(self.info(stack))

    terminate()
    sleep(5)
    kill(getpid(), SIGKILL)

_watcher = _Watcher()

class WatchLock(object):
  __lock_count = 0
  __intr_lock  = _allocate_lock()

  def __init__(self):
    self.__lock = _allocate_lock()
    with WatchLock.__intr_lock:
      self.__name = "WatchLock-%i" % WatchLock.__lock_count
      WatchLock.__lock_count += 1

  def __repr__(self):
    return "<%s>" % (self.__class__.__name__)

  def __str__(self):
    return self.__name

  def acquire(self, blocking=True):
    if not blocking:
      status = self.__lock.acquire(False)
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
    _watcher.release(self, self.__lock.release)

  def __exit__(self, t, v, bt):
    self.release()

  def locked(self):
    return self.__lock.locked()

class WatchRLock(threading._RLock):
  __lock_count = 0
  __intr_lock  = _allocate_lock()

  def __init__(self):
    threading._RLock.__init__(self)
    self._RLock__block = WatchLock()
    with WatchRLock.__intr_lock:
      self.__name = "WatchRLock-%i" % WatchRLock.__lock_count
      WatchRLock.__lock_count += 1

  def __str__(self):
    return self.__name

Lock = WatchLock
RLock = WatchRLock
