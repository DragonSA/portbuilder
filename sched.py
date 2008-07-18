"""
The schedular module.  This module handles the execution of time consuming tasks
in an effiecient manor.  It allows transparent concurrent task execution, this
allows a speedup on many machines.  
"""
from Queue import Queue

build_queue = Queue()  #: Queue for building ports
fetch_queue = Queue()  #: Queue for fetching distribution files
ports_queue = Queue()  #: Queue for fetching ports information

class WorkerPool(object):
  """
     The WorkerPool class.  This class manages a pool of worker threads for a
     specific queue.
  """

  def __init__(self, queue, number=1):
    """
       Initialise a worker thread pool

       @param queue: The queue the workers work for
       @type queue: C{Queue}
       @param number: The number of workers to allocate
       @type number: C{int}
    """
    from threading import Thread, RLock
    self._lock = RLock()
    self._number = number
    self._queue = queue

    self._pool = [Thread(target=self.worker) for i in xrange(number)]
    for i in self._pool:
      i.start()

  def __len__(self):
    """
       The size of the worker pool
    """
    return len(self._pool)

  def worker(self):
    """
       The worker.  It waits for a job from the queue and then executes the
       given command (with given parameters).
    """
    while True:
      cmd = self._queue.get()
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

      func(*args, **kwargs)

      self._queue.task_done()

build_pool = WorkerPool(build_queue)  #: Pool of port builder workers
fetch_pool = WorkerPool(fetch_queue)  #: Pool of port distfiles fetcher workers
ports_pool = WorkerPool(ports_queue)  #: Pool of port information workers
