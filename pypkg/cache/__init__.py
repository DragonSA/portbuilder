"""
The Cache module.  This module stores various items of information statically.
"""
from __future__ import absolute_import

from pypkg.cache.cachedb import CacheDB

__all__ = ['db', 'check_files', 'set_files']

db = CacheDB()  #: The databases used for caching

def check_files(db_name, name):
  """
     Check that the a set of files have not changed since the timestamp was
     taken.

     @param db_name: The database containing the timestamps
     @type db_name: C{str}
     @param name: The name that references the set of files
     @type name: C{str}
     @return: If the files have not changed
     @rtype: C{bool}
  """
  from cPickle import loads
  from os.path import exists, getmtime, getsize

  files = db[db_name].get(name)

  if not files:
    return False

  try:
    files = loads(files)
  except BaseException:
    from logging import getLogger
    getLogger('pypkg.cache').warn('Corrupt data detected (%s.%s)' %
                                                               (db_name, name))
    return False

  f_list = []
  for path, stats in files:
    if exists(path):
      if not stats or stats != (getmtime(path), getsize(path)):
        return False
    elif stats:
      return False
    f_list.append(path)
    
  return f_list

def set_files(db_name, name, files):
  """
     Sets the timestamps for a given set of files.

     @param db_name: The database containing the timestamps
     @type db_name: C{str}
     @param name: The name that references the set of files
     @type name: C{str}
     @param files: The set of files
     @type files: C{[str]}
  """
  from cPickle import dumps
  from os.path import exists, getmtime, getsize

  data = []
  for i in files:
    if exists(i):
      data.append((i, (getmtime(i), getsize(i))))
    else:
      data.append((i, None))

  db[db_name].put(name, dumps(data, -1))
