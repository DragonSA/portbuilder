"""
The Queue module.  This module handles the execution of time consuming tasks.
"""
from __future__ import with_statement

from Queue import Queue

class WorkerQueue(Queue):
  """
     The WorkerQueue class.  This class manages a pool of worker threads for
     running jobs.
  """

  def __init__(self, name, workers=1, idle=1):
    """
       Initialise a worker thread pool

       @param name: The name of this thread (used in logging)
       @type name: C{str}
       @param number: The number of workers to allocate
       @type number: C{int}
       @param idle: The idle time a worker waits before quits
       @type idle: C{int}
    """
    Queue.__init__(self)
    from threading import Lock
    self._idle = idle  #: The idle count for a worker
    self._lock = Lock()  #: Global lock for the class
    self._name = name  #: The name of this queue
    self._workers = workers  #: The (maximum) number of workers

    self._worker_cnt = 0  #: The number of workers created
    self._job_cnt = 0  #: The number of jobs executed

    self._pool = []  #: The pool of workers

  def __len__(self):
    """
       The size of the worker pool

       @return: The worker pool size
       @rtype: C{str}
    """
    return len(self._pool)

  def idle(self):
    """
       The idle time till a worker quits

       @return: The idle time
       @rtype: C{int}
    """
    return self._idle

  def setidle(self, idle):
    """
       Sets the idle time till a worker quits (this will not affect workers that
       are currently idle)

       @param idle: The idle time
       @type: C{str}
    """
    self._idle = idle

  def pool(self):
    """
       The number of workers in the pool.  The actual number may vary but will
       stabalise to this number under full load

       @return: Number of workers
       @rtype: C{int}
    """
    return self._workers

  def setpool(self, workers):
    """
       Changes the number of workers in the pool.  If more workers are currently
       running then some workers will be stopped after finishing their current
       job.

       @param workers: Number of workers
       @type workers: C{int}
    """
    self._workers = workers

  def put(self, item, block=True, timeout=0):
    """
       Places a job onto the queue, if insufficient workers are available one
       will be started.

       @param item: The job to execute
       @type item: C{(func, (args), \{kwargs\})}
    """
    Queue.put(self, item, block, timeout)
    with self._lock:
      if self.qsize() > 0 and len(self._pool) < self._workers:
        from threading import Thread
        self._pool.append(Thread(target=self.worker))
        self._pool[-1].start()

  def stats(self):
    """
       Returns a tuple about activity on the queue.
       (Workers running, Workers created, Jobs run(ning))

       @return: The tuple of information
       @rtype: C{(int, int, int)}
    """
    return (len(self), self._worker_cnt, self._job_cnt)

  def worker(self):
    """
       The worker.  It waits for a job from the queue and then executes the
       given command (with given parameters).
    """
    from threading import currentThread
    from Queue import Empty

    with self._lock:
      wid = self._worker_cnt
      self._worker_cnt += 1
    while True:
      with self._lock:
        if self._workers > len(self._pool):
          self._pool.remove(currentThread())
          return

        try:
          cmd = self.get(timeout=self._idle)
          jid = self._job_cnt
          self._job_cnt += 1
        except Empty:
          self._pool.remove(currentThread())
          return

      if len(cmd) == 1:
        func = cmd[0]
        args = []
        kwargs = {}
      elif len(cmd) == 2:
        func, args = cmd
        kwargs = {}
      elif len(cmd) == 3:
        func, args, kwargs = cmd
      else:
        # TODO: Error
        pass

      try:
        func(*args, **kwargs)
      except BaseException:
        # TODO: Something went wrong...
        pass

      self.task_done()

build_queue = WorkerQueue("Build")  #: Queue for building ports
fetch_queue = WorkerQueue("Fetch")  #: Queue for fetching distribution files
ports_queue = WorkerQueue("Ports")  #: Queue for fetching ports information