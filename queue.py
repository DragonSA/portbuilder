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
    # We have to use our own locks since we cannot access Queue's functions
    # without not holding the locks and doing this will cause a dead lock...
    self._lock = Lock()  #: The notifier and locker of this queue
    self._log = getLogger("pypkg.queue." + name)  #: Logger of this queue
    #self._name = name  #: The name of this queue
    self._workers = workers  #: The (maximum) number of workers

    self._worker_cnt = 0  #: The number of workers created
    self._job_cnt = 0  #: The number of jobs executed

    self._pool = {}  #: The pool of workers

  def __len__(self):
    """
       The size of the worker pool

       @return: The worker pool size
       @rtype: C{str}
    """
    return len(self._pool)

  def job(self, jid):
    """
       Returns if the specified job has finished or not

       @param jid: The job ID (as returns by put)
       @type jid: C{int}
       @return: If the job has finished
       @rtype: C{bool}
    """
    with self._lock:
      if jid in self._pool:
        return False
      for i in self.queue:
        if i[0] == jid:
          return False

      return True

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
    with self._lock:
      self._workers = workers

  def put(self, func, block=True, timeout=0):
    """
       Places a job onto the queue, if insufficient workers are available one
       will be started.

       @param func: The job to execute
       @type func: C{callable}
    """
    assert callable(func)
    with self._lock:
      # If there are no workers expected then we are not open for jobs
      if not self._workers:
        return -1
      jid = self._job_cnt
      self._job_cnt += 1
      Queue.put(self, (jid, func), block, timeout)
      if self.qsize() > 0 and len(self._pool) < self._workers:
        from threading import Thread
        thread = Thread(target=self._worker)
        self._pool[thread] = -1
        thread.setDaemon(True)
        thread.start()
      return jid

  def stats(self):
    """
       Returns a tuple about activity on the queue.
       (Workers running, Workers created, Jobs run(ning))

       @return: The tuple of information
       @rtype: C{(int, int, int)}
    """
    return (len(self), self._worker_cnt, self._job_cnt)

  def terminate(self):
    """
       Shutdown this WorkerQueue.  Unlike setpool(0) all remaining queued
       items are also removed.
    """
    from Queue import Empty

    self.setpool(0)
    try:
      while True:
        self.get(False)
        self.task_done()
    except Empty:
      return

  def _worker(self):
    """
       The worker.  It waits for a job from the queue and then executes the
       given command (with given parameters).
    """
    from threading import currentThread
    from Queue import Empty

    thread = currentThread()


    with self._lock:
      wid = self._worker_cnt
      self._worker_cnt += 1
    self._log.debug("Worker %d: Created" % wid)

    while True:
      with self._lock:
        try:
          if self._workers < len(self._pool):
            raise Empty
          jid, func = self.get(False)
          self._pool[thread] = jid
        except Empty:
          self._pool.pop(thread)
          self._log.debug("Worker %d: Terminating" % wid)
          return

      self._work(func, jid, wid)

      self.task_done()

      # Signal that a job has finished
      with self._lock:
        self._pool[thread] = -1

  def _work(self, func, jid, wid):
    """
       Execute a job

       @param func: The job to run
       @type func: C{callable}
       @param jid: The job's ID
       @type jid: C{int}
       @param wid: The worker's ID
       @type wid: C{int}
    """
    self._log.debug("Worker %d: Starting job %d" % (wid, jid))

    try:
      func()
    except KeyboardInterrupt:
      from tools import terminate
      terminate()
    except BaseException:
      self._log.exception("Worker %d: Job %d threw an exception"
                          % (wid, jid))
    finally:
      self._log.debug("Worker %d: Finished job %d" % (wid, jid))

config_queue  = WorkerQueue("config", 1)  #: Queue for configuring port options
build_queue   = WorkerQueue("build", ncpu)  #: Queue for building ports
fetch_queue   = WorkerQueue("fetch", 1)  #: Queue for fetching dist files
install_queue = WorkerQueue("install", 1)  #: Queue for installing ports
ports_queue   = WorkerQueue("ports", ncpu * 2)  #: Queue for fetching port info
queues        = [config_queue, build_queue, fetch_queue, install_queue,
                 ports_queue]  #: List of all the queues
