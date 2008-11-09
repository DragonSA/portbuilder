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
    if stats != getstats(path):
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

  data = []
  for i in files:
    data.append((i, getstats(i)))

  db[db_name].put(name, dumps(data, -1))

def getstats(path, cache=dict()):
  """
     Get the statistics on a given file.  Uses cache when possible.

     @param path: The file to get the stats on.
     @type path: C{str}
     @param cache: The cache of statistics
     @type cache: C{\{str:[(float, int), int]\}}
     @return: The files statistics
     @rtype: C{(float, int)
  """
  from os.path import exists, getmtime, getsize

  if cache.has_key(path) and cache[path][1] > 2:
    return cache[path][0]

  if exists(path):
    stats = (getmtime(path), getsize(path))
  else:
    stats = None

  if cache.has_key(path):
    cstats = cache[path]
    if cstats[0] == stats:
      cstats[1] += 1
    else:
      cstats[0] = stats
      cstats[1] = 0
  else:
    cache[path] = [stats, 0]

  return stats
