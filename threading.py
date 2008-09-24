from __future__ import with_statement

from stackless import channel, getcurrent, getruncount, run, schedule, tasklet
from tools import invert

# TODO: Add _is_owned
# TODO: _release_save
# TODO: _acquire_restore
# TODO: Make TaskletExit safe

class LockForWith(object):
  def __enter__(self):
    self.acquire()

  def __exit__(self, t, v, bt):
    self.release()

class Atomic(LockForWith):
  def __init__(self):
    self._atomic = None
    self._owner = None
    self._count = 0

  def acquire(self):
    while self._owner and self._owner is not getcurrent():
      schedule()
    assert self._owner is None or (self._count and self._owner is getcurrent())
    self._count += 1
    if self._count > 1:
      return
    self._owner = getcurrent()
    self._atomic = self._owner.set_atomic(True)

  def release(self):
    while self._owner is not getcurrent():
      schedule()
    assert self._owner is getcurrent() and self._count > 0
    self._count -= 1
    if self._count > 0:
      return
    rel = self._owner.set_atomic
    atom = self._atomic
    self._owner = None
    self._atomic = None
    rel(atom)

atomic = Atomic()

def send_nowait(channel, message):
  tasklet(channel.send)(message)

class Lock(LockForWith):
  def __init__(self):
    self._owner = None
    self._channel = channel()
    self._waiting = 0

  def acquire(self, blocking=True):
    current = getcurrent()
    if not blocking and self._owner is not current:
      return False

    while True:
      with atomic:
        if self._owner is None:
          self._owner = current
          return True
        else:
          self._waiting += 1
      self._channel.receive()

  def locked(self):
    return self._owner is not None

  def release(self, override=False):
    assert self._is_owned() or override
    with atomic:
      self._owner = None
      if self._waiting:
        self._waiting -= 1
        send_nowait(self._channel, None)

  def _is_owned(self):
    return self._owner is getcurrent()

class RLock(Lock):
  def __init__(self):
    Lock.__init__(self)
    self._count = 0

  def acquire(self, blocking=True):
    current = getcurrent()
    if self._owner is current:
      self._count += 1
      return True

    status = Lock.acquire(self, blocking)
    if status:
      assert self._count == 0
      self._count += 1
    return status

  def release(self):
    assert self._count > 0 and self._owner is getcurrent()
    with atomic:
      self._count -= 1
      if not self._count:
        Lock.release(self)

class Condition(LockForWith):
  def __init__(self, lock=None):
    if lock:
      self._lock = lock
    else:
      self._lock = RLock()
    self.acquire = self._lock.acquire
    self.release = self._lock.release
    self._is_owned = self._lock._is_owned
    self._waiters = []

  def wait(self, timeout=0):
    assert self._is_owned()
    waiter = Lock()
    waiter.acquire()
    self._waiters.append(waiter)

    with invert(self._lock):
      # TODO, add timeout
      if not timeout:
        with waiter:
          return True
      return False

  def notify(self, n=1):
    assert self._is_owned()
    with atomic:
      for i in self._waiters[:n]:
        i.release(override=True)
        self._waiters.remove(i)

  def notifyAll(self):
    self.notify(len(self._waiters))

class Semaphore(LockForWith):
  def __init__(self, value=1):
    self._cond = Condition(Lock())
    self._value = value

  def acquire(self, blocking=True):
    with self._cond:
      if self._value == 0:
        if not blocking:
          return False
        else:
          return self._cont.wait()  # Should always return True
      else:
        self._value -= 1
        return True

  def release(self):
    with self._cond:
      self._value += 1
      self._conf.notify()

class BoundedSemaphore(Semaphore):
  def __init__(self, value=1):
    Semaphore.__init__(self, value)
    self._bound = value

  def release(self):
    assert self._value < self._bound
    Semaphore.release(self)

# Helper to generate new thread names
_counter = 0
def _newname(template="Thread-%d"):
    global _counter
    _counter = _counter + 1
    return template % _counter

# Active thread administration
_active_limbo_lock = Lock()
_active = {}    # maps thread id to Thread object
_limbo = {}

class Thread(object):
  def __init__(self, group=None, target=None, name=None, args=(), kwargs=None):
    assert group is None
    if kwargs is None:
      kwargs = {}
    self.__target = target
    self.__name = str(name or _newname())
    self.__args = args
    self.__kwargs = kwargs
    self.__ident = None
    self.__started = False
    self.__stopped = False
    self.__block = Condition(Lock())
    self.__initialized = True

  def start(self):
    assert not self.__started
    with _active_limbo_lock:
      task = tasklet(self.__bootstrap)
      _limbo[task] = self
    task()

  def join(self, timeout=0):
    assert self.__started and self.__ident is not getcurrent()
    with self.__block:
      if self.__stopped:
        return True
      self.__block.wait(timeout)
      return self.__stopped

  def run(self):
    try:
      if self.__target:
        self.__target(*self.__args, **self.__kwargs)
    finally:
      del self.__target, self.__args, self.__kwargs

  def __bootstrap(self):
    self.__ident = getcurrent()
    self.__started = True
    with _active_limbo_lock:
      _active[self.__ident] = self
      del _limbo[self.__ident]

    try:
      self.run()
    except:
      # TODO
      raise
    finally:
      with _active_limbo_lock:
        del _active[self.__ident]
      self.__stopped = True
      with self.__block:
        self.__block.notifyAll()

  def getName(self):
    return self.__name

def currentThread():
  return _active[getcurrent()]

def start(opt_code_count=1000):
  while getruncount() > 1 or len(_active):
    task = run(opt_code_count)
    if task:
      task.insert()

class LocalProxy(object):
  __store = {}

  @staticmethod
  def __local():
    current = getcurrent()
    if not LocalProxy.__store.has_key(current):
      LocalProxy.__store[current] = {}
    return LocalProxy.__store[current]

  def __call__(self):
    return self

  def __getattribute__(self, name):
    return LocalProxy.__local()[name]

  def __setattr__(self, name, value):
    LocalProxy.__local()[name] = value

  def __delattr__(self, name):
    return LocalProxy.__local().pop(name)

  def __del__(self):
    try:
      LocalProxy.__store.pop(getcurrent())
    except ValueError:
      pass

local = LocalProxy()

def _shutdown():
  pass