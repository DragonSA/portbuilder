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
  root_dbdir = 'var/db/pypkg'
  if getenv('USER') == 'root':
    dirs['db']      = root_dbdir # {DB_ROOT}
    dirs['db_root'] = dirs['db'] # ${DB}
  else:
    dirs['db']      = join(dirs['home'], 'cache') # ${PYPKG}/db
    if isdir(root_dbdir):
      dirs['db_root'] = root_dbdir # {DB_ROOT}
    else:
      dirs['db_root'] = dirs['db'] # ${DB}
  dirs['db_log'] = join(dirs['db'], 'log') # ${PYPKG}/${DB}/log
  dirs['db_tmp'] = '/tmp/pypkg'            # ${TMPDIR}/pypkg

  dirs['db_root_log'] = join(dirs['db'], 'log') # ${ROOT_DB}/log
  dirs['db_root_tmp'] = '/tmp/pypkg'            # ${TMPDIR}/pypkg

  # The log dir
  dirs['log']      = '/tmp/pypkg' #join(dirs['home'], 'log') # ${PYPKG}/log
  dirs['log_port'] = '/tmp/pypkg' # ${TMPDIR}/pypkg

  # The config dir
  dirs['config'] = dirs['home']  # ${PYPKG}

  all_dirs = dirs.values()
  all_dirs.sort()
  for i in all_dirs:
    if not isdir(i):
      mkdir(i)

def init_files():
  """
     Initialise the local files.
  """
  from os.path import join

  files['log'] = join(dirs['log'], 'pypkg.log')

def init_names():
  """
     Initialise the names alias
  """
  names['port.attr']      = 'port_attr.db'      # The port attributes
  names['port.makefiles'] = 'port_makefiles.db' # Makefiles included by a port
  names['distfiles']      = 'distfiles.db'      # The ports distribution files

init_dirs()
init_files()
init_names()
