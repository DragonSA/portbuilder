"""
The Cache module.  This module stores various items of information statically.
"""
from __future__ import absolute_import, with_statement

from .cachedb import CacheDB
from ..threads import Lock

__all__ = ['db', 'no_cache', 'check_files', 'set_files']

db = CacheDB()  #: The databases used for caching
no_cache = False #: Indicate if caching should tage place

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
  if no_cache:
    return False

  files = db[db_name].get(name)

  if not files:
    if db[db_name].has_key(name):
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
  if isinstance(files, str):
    files = (files,)

  if not no_cache:
    data = []
    for i in files:
      data.append((i, getstats(i)))

    db[db_name][name] = data

def getstats(path, cache=dict(), lock=Lock()):
  """
     Get the statistics on a given file.  Uses cache when possible.

     @param path: The file to get the stats on.
     @type path: C{str}
     @param cache: The cache of statistics
     @type cache: C{\{str:[(float, int), int]\}}
     @param lock: The lock for the cache
     @type lock: C{Lock}
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

  with lock:
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
