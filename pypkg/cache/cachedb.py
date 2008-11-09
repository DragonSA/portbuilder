"""
The cachedb module.  This modules has the cache database storage class.
"""
from __future__ import absolute_import, with_statement

__all__ = ['CacheDB']

class CacheDB(object):
  """
     The CacheDB class.  This class manages the various databases.
  """

  def __init__(self):
    """
       Initialise the database environment.
    """
    from bsddb.db import DBEnv, DB_CREATE, DB_INIT_CDB, DB_INIT_MPOOL
    from threading import Lock

    from pypkg.env import dirs

    self._dbcache = {}
    self._env = DBEnv()
    self.__lock = Lock()

    self._env.set_data_dir(dirs['db'])
    self._env.set_lg_dir(dirs['db_log'])
    self._env.set_tmp_dir(dirs['db_tmp'])
    self._env.open(dirs['db'], DB_CREATE | DB_INIT_CDB | DB_INIT_MPOOL)

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
          self._dbcache[key] = new_db
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
