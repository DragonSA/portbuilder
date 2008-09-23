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
    from atexit import register
    from logging import getLogger
    from threading import Condition, Lock, local
    # We have to use our own locks since we cannot access Queue's functions
    # without not holding the locks and doing this will cause a dead lock...
    self._lock = Condition(Lock())  #: The notifier and locker of this queue
    self._log = getLogger("pypkg.queue." + name)  #: Logger of this queue
    #self._name = name  #: The name of this queue
    self._workers = workers  #: The (maximum) number of workers

    self._worker_cnt = 0  #: The number of workers created
    self._job_cnt = 0  #: The number of jobs executed

    self._pool = {}  #: The pool of workers
    self._local = local()  #: Thread specific information

    register(lambda: self.setpool(0))

  def __len__(self):
    """
       The size of the worker pool

       @return: The worker pool size
       @rtype: C{str}
    """
    return len(self._pool)

  def condition(self):
    """
       The condition that is issued everytime a job finishes

       @return: The condition object
       @rtype: C{Condition}
    """
    return self._lock

  def job(self, jid):
    """
       Returns if the specified job has finished or not

       @param jid: The job ID (as returns by put)
       @type jid: C{int}
       @return: If the job has finished
       @rtype: C{bool}
    """
    with self._lock:
      if jid in self._pool.itervalues():
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
    self._workers = workers

  def put(self, func, block=True, timeout=0):
    """
       Places a job onto the queue, if insufficient workers are available one
       will be started.

       @param func: The job to execute
    """
    with self._lock:
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

  def put_wait(self, func):
    """
       Place a job onto the queue and then wait for it to be executed

       @param func: The job to execute
    """
    from threading import currentThread
    with self._lock:
      if currentThread in self._pool.iterkeys():
        jid = self._job_cnt
        inline = True
      else:
        inline = False

    if inline:
      self._work(func, jid)
    else:
      jid = self.put_nowait(func)
      self.wait(lambda: self.job(jid))

  def stats(self):
    """
       Returns a tuple about activity on the queue.
       (Workers running, Workers created, Jobs run(ning))

       @return: The tuple of information
       @rtype: C{(int, int, int)}
    """
    return (len(self), self._worker_cnt, self._job_cnt)

  def wait(self, func):
    """
       Wait until a curtain criteria has been met.  The criteria is checked
       every time a job has been finished.

       @param func: The criteria
       @type func: C{function}
    """
    from threading import currentThread
    with self._lock:
      if currentThread() in self._pool.iterkeys():
        self._log.error("Worker %i: Job %i is waiting on its own queue" %
                        (self._local.jid, self._local.wid))
        raise RuntimeError, "Averted dead lock on queue"
      while True:
        if func() or len(self) == 0:
          return
        self._lock.wait()

  def _worker(self):
    """
       The worker.  It waits for a job from the queue and then executes the
       given command (with given parameters).
    """
    from threading import currentThread
    from Queue import Empty

    thread = currentThread()

    with self._lock:
      self._local.wid = self._worker_cnt
      self._worker_cnt += 1
    self._log.debug("Worker %d: Created" % self._local.wid)

    while True:
      with self._lock:
        try:
          if self._workers < len(self._pool):
            raise Empty
          self._local.jid, func = self.get(False)
          self._pool[thread] = self._local.jid
        except Empty:
          self._pool.pop(thread)
          self._lock.notifyAll()
          self._log.debug("Worker %d: Terminating" % self._local.wid)
          return

      self._work(func, self._local.jid)

      self.task_done()

      # Signal that a job has finished
      with self._lock:
        self._pool[thread] = -1
        self._lock.notifyAll()

  def _work(self, func, jid):
    """
       Execute a job

       @param func: The job to run
       @param jid: The job's ID
       @type jid: C{int}
    """
    self._log.debug("Worker %d: Starting job %d" % (self._local.wid, jid))

    try:
      func()
    except TypeError:
      self._log.exception("Worker %d: Job %d didn't specify a callable target"
                          % (self._local.wid, jid))
    except BaseException:
      self._log.exception("Worker %d: Job %d threw an exception"
                          % (self._local.wid, jid))
    finally:
      self._log.debug("Worker %d: Finished job %d" % (self._local.wid, jid))

config_queue  = WorkerQueue("config", 1)  #: Queue for configuring port options
build_queue   = WorkerQueue("build", ncpu)  #: Queue for building ports
fetch_queue   = WorkerQueue("fetch", 1)  #: Queue for fetching dist files
install_queue = WorkerQueue("install", 1)  #: Queue for installing ports
ports_queue   = WorkerQueue("ports", ncpu * 2)  #: Queue for fetching port info
