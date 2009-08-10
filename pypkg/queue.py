"""
The Queue module.  This module handles the execution of time consuming tasks.
"""
from __future__ import absolute_import, with_statement

from subprocess import Popen, PIPE

#: The number of CPU's available on this system
ncpu = int(Popen(['sysctl', '-n', 'hw.ncpu'], stdout=PIPE).communicate()[0])

class WorkerQueue(object):
  """
     The WorkerQueue class.  This class manages a pool of worker threads for
     running jobs.
  """

  def __init__(self, name, load=1):
    """
       Initialise a worker thread pool

       @param name: The name of this thread (used in logging)
       @type name: C{str}
       @param load: The maximum load allowed
       @type load: C{int}
    """
    from logging import getLogger
    from .threads import Condition, Lock
    # We have to use our own locks since we cannot access Queue's functions
    # without not holding the locks and doing this will cause a dead lock...
    lname = name[0].upper() + name[1:] + "QueueLock"
    self._lock = Condition(Lock(lname))  #: The locker of this queue
    self._log = getLogger("pypkg.queue." + name)  #: Logger of this queue
    self._name = name  #: The name of this queue
    self._load = load  #: The requested load
    self._curload = 0  #: The current load experianced

    self._wid = 0  #: The number of workers created (and next WID)
    self._jid = 0  #: The number of jobs created (and next JID)

    self._pool = {}  #: The pool of workers
    self._queue = []  #: Queue of jobs
    self._stalled = []  #: The stalled workers (with load and waker)

  def __len__(self):
    """
       The size of the worker pool

       @return: The worker pool size
       @rtype: C{int}
    """
    return len(self._pool) - len(self._stalled)

  def qsize(self):
    """
       The size of the queued items

       @return: The queue size
       @rtype: C{int}
    """
    return len(self._queue) + len(self._stalled)

  def jid(self):
    """
       Returns the current job ID.  Can only be called from a worker thread.

       @return: The current workers JID
       @rtype: C{int}
    """
    from .threads import current_thread

    return self._pool[current_thread()][1]

  def job(self, jid):
    """
       Returns if the specified job has finished or not

       @param jid: The job ID (as returns by put)
       @type jid: C{int}
       @return: If the job has finished
       @rtype: C{bool}
    """
    with self._lock:
      for i in self._pool:
        if i[1] == jid:
          return False
      for i in self._queue:
        if i[1] == jid:
          return False

      return True

  def join(self):
    """
       Wait till all jobs have been consumed.
    """
    with self._lock:
      if self._pool:
        self._lock.wait()

  def load(self):
    """
       The current load allowed.  The actual number may vary but will hover
       around this figure.

       @return: Number of workers
       @rtype: C{int}
    """
    return self._workers

  def set_load(self, load):
    """
       Changes the current requested load.

       @param load: The load
       @type load: C{int}
    """
    with self._lock:
      self._load = load

      if not load:
        while self._stalled:
          worker = self._stalled.pop()
          self._curload += worker[1]
          worker[0].release()

  def put(self, func, load=1):
    """
       Places a job onto the queue, if insufficient workers are available one
       will be started.

       @param func: The job to execute
       @type func: C{callable}
       @param load: The load the job
       @type load: C{int}
    """
    assert callable(func)
    with self._lock:
      # If there is no load allowed then we are not open for jobs
      if not self._load:
        return -1

      self._jid += 1

      self._queue.append((func, self._jid, load))
      self._start()

      return self._jid

  def stats(self):
    """
       Returns a tuple about activity on the queue.
       (Workers running, Workers created, Jobs created)

       @return: The tuple of information
       @rtype: C{(int, int, int)}
    """
    return (len(self), self._wid, self_jid)

  def stalled(self):
    """
       Indicates if a worker has stalled.  This will result in a worker being
       created to replace this worker.

       NOTE: Can only be called from within a job

       @return: If stalling is possible
       @rtype: C{bool}
    """
    from .threads import current_thread, WatchLock as Lock

    wid, jid, load = self._pool[current_thread()]
    lock = Lock("StalledLock",  True)

    with lock:
      with self._lock:
        if not self._load:
          return False

        self._log.debug("Worker %d: Job %d stalled")
        self._stalled.append((lock, load))
        self._curload -= load
        self._start()

      # Wait for a worker to finish
      lock.acquire()
      self._log.debug("Worker %d: Job %d resuming")
      # `self._curload += load` called by waker
      # `self._stalled.remove((lock, load))` called by waker

    return bool(self._load)

  def terminate(self):
    """
       Shutdown this WorkerQueue.  Unlike set_load(0) all remaining queued
       items are also removed.
    """
    from Queue import Empty

    self.set_load(0)
    self._queue = []

  def _start(self):
    """
       Starts a worker if there is a need.

       NOTE: Must be called with lock held
    """
    assert not self._lock.acquire(False)

    while self._queue and self._curload < self._load:
      from .threads import Thread

      job = self._find_job()

      self._wid += 1
      thread = Thread(target=lambda: self._worker(self._wid, job))
      self._pool[thread] = (self._wid,) + job[1:]
      self._curload += job[2]

      thread.start()

  def _find_job(self):
    """
       Finds an appropriate job to run.

       NOTE: Must be called with lock held (and len(self._queue) > 0)

       @return: The job to run
       @rtype: C{Callable, int, int}
    """
    assert not self._lock.acquire(False)
    assert self._curload < self._load and self._queue

    load = self._load - self._curload

    job = 0

    for i in xrange(len(self._queue)):
      if self._queue[i][2] <= load:
        return self._queue.pop(i)
      if self._queue[i][2] < self._queue[job][2]:
        job = i

    return self._queue.pop(job)

  def _find_worker(self):
    """
       Finds an appropriate stalled worker to run.

       NOTE: Must be called with lock held (and len(self._stalled) > 0)

       @return: The worker to wake
       @rtype: C{Lock, int}
    """
    assert not self._lock.acquire(False)
    assert self._curload < self._load and self._stalled

    load = self._load - self._curload

    worker = 0

    for i in xrange(len(self._stalled)):
      if self._stalled[i][1] <= load:
        return self._stalled.pop(i)
      if self._stalled[i][1] < self._stalled[worker][1]:
        worker = i

    return self._stalled.pop(worker)

  def _worker(self, wid, job):
    """
       The worker.  It waits for a job from the queue and then executes the
       given command (with given parameters).

       @param wid: The worker ID
       @type wid: C{int}
       @param job: The first job to run
       @type job: C{Callable, int, int}
    """
    from .threads import current_thread
    from Queue import Empty

    thread = current_thread()
    thread.name = self._name[0].upper() + self._name[1:] + "Worker-%i" % wid

    self._log.debug("Worker %d: Created" % wid)

    while True:
      func, jid, load = job

      self._work(func, jid, wid)

      # Signal that a job has finished
      with self._lock:
        self._curload -= load

        while self._stalled and self._curload < self._load:
          lock, load = self._find_worker()
          self._curload += load
          lock.release()

        if self._curload >= self._load or not self._queue:
          break

        job = self._find_job()
        self._curload += job[2]
        self._start()

    self._pool.pop(thread)
    self._log.debug("Worker %d: Terminating" % wid)
    if not self._pool:
      with self._lock:
        self._lock.notifyAll()

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
      from .exit import terminate
      terminate()
    except BaseException:
      self._log.exception("Worker %d: Job %d threw an exception" % (wid, jid))
    finally:
      self._log.debug("Worker %d: Finished job %d" % (wid, jid))

config_queue  = WorkerQueue("config", 1)  #: Queue for configuring port options
build_queue   = WorkerQueue("build", ncpu + 1)  #: Queue for building ports
fetch_queue   = WorkerQueue("fetch", 2)  #: Queue for fetching dist files
install_queue = WorkerQueue("install", 1)  #: Queue for installing ports
ports_queue   = WorkerQueue("ports", ncpu * 2)  #: Queue for fetching port info
queues        = [config_queue, build_queue, fetch_queue, install_queue,
                 ports_queue]  #: List of all the queues
