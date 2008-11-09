"""
The cachedb module.  This modules has the cache database storage class.
"""
from __future__ import absolute_import, with_statement

from contextlib import contextmanager

__all__ = ['CacheDB']

class CacheDB(object):
  """
     The CacheDB class.  This class manages the various databases.
  """

  def __init__(self):
    """
       Initialise the database environment.
    """
    from bsddb.db import DBEnv, DB_CREATE, DB_RECOVER, DB_THREAD
    from bsddb.db import DB_INIT_LOCK, DB_INIT_LOG, DB_INIT_MPOOL, DB_INIT_TXN
    from bsddb.db import DB_AUTO_COMMIT #, DB_DIRECT_DB, DB_DIRECT_LOG
    from threading import Lock

    from pypkg.env import dirs

    self._dbcache = {}
    self._env = DBEnv()
    self.__lock = Lock()

    self._env.set_flags(DB_AUTO_COMMIT, 1) # | DB_DIRECT_DB | DB_DIRECT_LOG, 1)
    self._env.set_data_dir(dirs['db'])
    self._env.set_lg_dir(dirs['db_log'])
    self._env.set_tmp_dir(dirs['db_tmp'])
    self._env.open(dirs['db'], DB_CREATE | DB_RECOVER | DB_THREAD |
                      DB_INIT_LOCK | DB_INIT_LOG | DB_INIT_MPOOL | DB_INIT_TXN)

    self.__count = 0.

  def __getitem__(self, key):
    """
       Retrieve a database.

       @param key: The name of the database
       @type key: C{str}
       @return: The database
       @rtype: C{DB}
    """
    from pypkg.env import names
    
    try:
      return self._dbcache[names.get(key, key)]
    except KeyError:
      key = names.get(key, key)
      with self.__lock:
        if not self._dbcache.has_key(key):
          from bsddb.db import DB, DB_HASH, DB_CREATE
          new_db = DB(self._env)
          new_db.open(key, dbtype=DB_HASH, flags=DB_CREATE)
          self._dbcache[key] = DBProxy(new_db)
      return self._dbcache[key]

  def close(self):
    """
       Close all the databases (and the environment)
    """
    for dbs in self._dbcache.itervalues():
      dbs.close()
    self._env.close()

  def get(self, key):
    """
       Retrieve a database.

       @param key: The name of the database
       @type key: C{str}
       @return: The database
       @rtype: C{DB}
    """
    return self[key]

class DBProxy(object):
  """
     Provide a dictionary like interface to a BSD database.  Proper locking
     is implemented.
  """

  def __init__(self, bsddb):
    """
       Initialise the database's proxy.

       @param db: The database
       @type db: C{DB}
    """
    self.__db = bsddb
    self.__lock = RWLock()

  def __getitem__(self, key):
    """
       Retrieve the value referenced by the key.

       @param key: The key
       @return: The value
    """
    from cPickle import dumps, loads

    try:
      with self.__lock.read_lock:
        return loads(self.__db.get(dumps(key, -1)))
    except BaseException:
      raise KeyError, key

  def __setitem__(self, key, value):
    """
       Set the value referenced by key.

       @param key: The key
       @param value: The value
    """
    from cPickle import dumps

    with self.__lock.write_lock:
      self.__db.put(dumps(key, -1), dumps(value, -1))

  def get(self, key, default=None):
    """
       Retrieve the value refernced by the key and if it does not exist return
       default.

       @param key: The key
       @param default: The return value if key does not exist
       @return: The value or default
    """
    try:
      return self[key]
    except KeyError:
      return default

  def has_key(self, key):
    """
       Indicates if the database has the key.

       @return: If the database has the key
       @rtype: C{bool}
    """
    from cPickle import dumps
    
    with self.__lock.read_lock:
      if self.__db.get(dumps(key)):
        return True
    return False

  def close(self):
    """
       Close the database.
    """
    with self.__lock.write_lock:
      self.__db.close()

class RWLock(object):
  """
     A Read Write Lock.  This allows many readers to simultaniously hold the
     lock while only one writer may.
  """

  # Various states that the RWLock can be in
  READ_LOCK = 1  # A read lock is held
  WRITE_LOCK = 2 # A write lock is held

  READ_PENDING = READ_LOCK   # A read lock request is pending
  WRITE_PENDING = WRITE_LOCK # A write lock request is pending

  def __init__(self):
    """
       Initialise the lock.
    """
    from threading import Condition, Lock

    self.__lock = Lock()
    self.__rcond = Condition(self.__lock)
    self.__wcond = Condition(self.__lock)

    self.__readers = []
    self.__readers_queue = 0
    self.__writer = None
    self.__writer_queue = 0

  def acquire_read(self, blocking=True):
    """
       Acquire a read lock.

       @param blocking: If we should wait for the lock
       @type blocking: C{bool}
       @return: If we got the lock
       @rtype: C{bool}
    """
    from threading import currentThread

    me = currentThread()

    if me in self.__readers:
      raise RuntimeError, "Cannot acquire read-lock when already held"

    with self.__lock:
      if not self.__writer:
        self.__readers.append(me)
        return True
      elif not blocking:
        return False

      self.__readers_queue += 1
      self.__rcond.wait()
      self.__readers_queue -= 1
      self.__readers.append(me)
      return True

  def release_read(self):
    """
       Release a read lock.
    """
    from threading import currentThread

    me = currentThread()

    if me not in self.__readers:
      raise RuntimeError, "Cannot release read-lock not held"
      
    with self.__lock:
      self.__readers.remove(me)
      if self.__writer is True and not len(self.__readers):
        self.__wcond.notify()

  def acquire_write(self, blocking=True):
    """
       Acquire a write lock.

       @param blocking: If we should wait for the lock
       @type blocking: C{bool}
       @return: If we got the lock
       @rtype: C{bool}
    """
    from threading import currentThread

    me = currentThread()

    if self.__writer is me:
      raise RuntimeError, "Cannot acquire write-lock when already held"

    with self.__lock:
      if len(self.__readers) and not self.__writer:
        if not blocking:
          return False
        self.__writer = True
        self.__wcond.wait()
        assert self.__writer is True and not len(self.__readers)

      elif self.__writer and self.__writer is not True:
        if not blocking:
          return False
        self.__writer_queue += 1
        self.__wcond.wait()
        self.__writer_queue -= 1

        assert self.__writer is True and not len(self.__readers)
        
      self.__writer = me
      return True

  def release_write(self):
    """
       Releases a write lock.
    """
    from threading import currentThread

    me = currentThread()

    if self.__writer is not me:
      raise RuntimeError, "Cannot release write-lock not held"

    with self.__lock:
      if self.__writer_queue:
        self.__writer = True
        self.__wcond.notify()
      else:
        self.__writer = None
        self.__rcond.notifyAll()

  def release(self):
    """
       Releases a lock.
    """
    if self.__writer and self.__writer is not True:
      self.release_write()
    else:
      self.release_read()

  def locked_read(self):
    """
       Indicate if the read lock is held
    """
    from threading import currentThread

    return currentThread() in self.__readers

  def locked_write(self):
    """
       Indicate if the write lock is held
    """
    from threading import currentThread

    return currentThread() is self.__writer

  def locked(self):
    """
        Indicate if the lock is held
    """
    if self.__writer and self.__writer is not True:
      return self.locked_write()
    else:
      return self.locked_read()

  def state(self):
    """
       The state of this lock.  If it is in read or write mode and which
       requests are pending.

       @return: The state:
       @rtype: C{(int, int)}
    """
    pending =  (self.__readers_queue and RWLock.READ_PENDING or 0)
    pending |= (self.__writer_queue and RWLock.WRITE_PENDING or 0)
    if self.__writer and self.__writer is not True:
      return RWLock.WRITE_LOCK, pending
    elif len(self.__readers):
      return RWLock.READ_LOCK, pending
    else:
      return 0, pending

  @property
  @contextmanager
  def read_lock(self):
    """
       The read lock.
    """
    self.acquire_read()
    try:
      yield
    finally:
      self.release_read()

  @property
  @contextmanager
  def write_lock(self):
    """
       The write lock.
    """
    self.acquire_write()
    try:
      yield
    finally:
      self.release_write()
