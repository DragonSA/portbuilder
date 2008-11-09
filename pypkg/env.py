"""
The directory module.  This module handles the directories to be used for
various other modules.
"""
from __future__ import absolute_import

__all__ = ['dirs', 'files', 'names']

dirs  = {}  #: The default directories
files = {}  #: The file names
names = {}  #: The aliases of names

def init_dirs():
  """
     Initialise the local directories.
  """
  from os.path import isdir, join
  from os import getenv, mkdir

  # The home directory for pypkg
  dirs['home'] = join(getenv('HOME'), '.pypkg')  # ${HOME}/.pypkg

  # The database dirs
  dirs['db']     = join(dirs['home'], 'cache') # ${PYPKG}/db
  dirs['db_log'] = join(dirs['db'], 'log')     # ${PYPKG}/${DB}/log

  # The log dir
  dirs['log'] = join(dirs['home'], 'log') # ${PYPKG}/log

  # The config dir
  dirs['config'] = dirs['home']  # ${PYPKG}

  all_dirs = dirs.values()
  all_dirs.sort()
  for i in all_dirs:
    if not isdir(i):
      # TODO: Error handling
      mkdir(i)

def init_files():
  """
     Initialise the local files.
  """
  pass

def init_names():
  """
     Initialise the names alias
  """
  names['port.attr'] = 'port_attr.db'
  names['distfiles'] = 'distfiles.db'

init_dirs()
init_files()
init_names()
