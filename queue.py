"""
The Queue module.  This module handles the execution of time consuming tasks.
"""
from __future__ import with_statement

from subprocess import Popen, PIPE
from Queue import Queue

#: The number of CPU's available on this system
ncpu = int(Popen(['sysctl', '-n', 'hw.ncpu'], stdout=PIPE).communicate()[0])

class WorkerQueue(Queue):
  """
     The WorkerQueue class.  This class manages a pool of worker threads for
     running jobs.
  """

  def __init__(self, name, workers=1):
    """
       Initialise a worker thread pool

       @param name: The name of this thread (used in logging)
       @type name: C{str}
       @param number: The number of workers to allocate
       @type number: C{int}
    """
    Queue.__init__(self)
    from logging import getLogger
    from threading import Lock
    self._lock = Lock()  #: Global lock for this class
    self._log = getLogger("pypkg.queue." + name)  #: Logger of this queue
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

  def logger(self):
    """
       The logger used by this queue

       @return: The logger
       @rtype:
    """
    return self._log

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
    with self._lock:
      Queue.put(self, item, block, timeout)
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
      self._log.debug("Worker %d: Created" % wid)
    while True:
      with self._lock:
        if self._workers < len(self._pool):
          self._pool.remove(currentThread())
          return

        try:
          cmd = self.get(False)
        except Empty:
          self._pool.remove(currentThread())
          return

        jid = self._job_cnt
        self._job_cnt += 1
        self._log.debug("Worker %d: Starting job %d" % (wid, jid))

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
        self._log.error("Worker %d: Job %d is malformed" % (wid, jid))
        self.task_done()
        continue

      try:
        func(*args, **kwargs)
      except BaseException:
        self._log.exception("Worker %d: Job %d threw an exception" % (wid, jid))
      else:
        self._log.debug("Worker %d: Finished job %d" % (wid, jid))

      self.task_done()

build_queue = WorkerQueue("build", ncpu)  #: Queue for building ports
fetch_queue = WorkerQueue("fetch", 1)  #: Queue for fetching distribution files
ports_queue = WorkerQueue("ports", ncpu * 2)  #: Queue for fetching port info