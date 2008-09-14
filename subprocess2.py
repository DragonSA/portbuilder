"""
The subprocess2 module.  This module is a derivative of subprocess.  It manages
a thread that handles all the creating requests of Popen.  This prevents some
locking contentions and makes sure only one Popen instance is executed at a time
"""

from __future__ import with_statement

import subprocess

__all__ = subprocess.__all__ + ['PopenQueue']

class _PopenQueue(object):
  def __init__(self):
    from atexit import register
    from collections import deque
    from threading import Condition, Lock, Thread
    self._lock = Lock()
    self._signal_client = Condition(self._lock)
    self._signal_worker = Condition(self._lock)

    self._terminate = False
    self._job_cnt = 0
    self._queue = deque()
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

        jid, args, kwargs = self._queue.popleft()

      self._popen[jid] = subprocess.Popen(close_fds=True, *args, **kwargs)

      with self._lock:
        self._signal_client.notifyAll()

  #def worker(self):
    #from os import fork, pipe
    #from pickle import dump, load

    #term_signal = (-1, None, None)

    #def fdpipe(pipe, mode):
      #from os import close, fdopen
      #if mode == 'r':
        #close(pipe[1])
        #return fdopen(pipe[0], mode)
      #elif mode == 'w':
        #close(pipe[0])
        #return fdopen(pipe[1], mode, 0)

    #Popen_stream = pipe()
    #Arg_stream = pipe()

    #pid = fork()
    #if pid:
      #Popen_stream = fdpipe(Popen_stream, 'r')
      #Arg_stream = fdpipe(Arg_stream, 'w')

      #while True:
        #with self._lock:
          #while len(self._queue) == 0 and not self._terminate:
            #self._signal_worker.wait()

          #if self._terminate:
            #dump(term_signal, file=Arg_stream, protocol=-1)
            #if term_signal != load(Popen_stream):
              ## TODO: something went wrong
              #pass
            #return

          #args = self._queue.popleft()

        #dump(args, file=Arg_stream, protocol=-1)
        #self._popen[args[0]] = load(Popen_stream)

        #with self._lock:
          #self._signal_client.notifyAll()

    #else:
      #Popen_stream = fdpipe(Popen_stream, 'w')
      #Arg_stream = fdpipe(Arg_stream, 'r')

      #while True:
        #jid, args, kwargs = load(Arg_stream)
        #if term_signal == (jid, args, kwargs):
          #dump(term_signal, file=Popen_stream, protocol=-1)
          #exit(255)
        #dump(subprocess.Popen(close_fds=True, *args, **kwargs),
             #file=Popen_stream, protocol=-1)

PopenQueue = _PopenQueue()
Popen = PopenQueue.put_wait

for i in __all__:
  if i not in locals():
    locals()[i] = getattr(subprocess, i)
