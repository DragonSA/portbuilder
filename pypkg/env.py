"""
The directory module.  This module handles the directories to be used for
various other modules.
"""

from os import getuid, getgroups

__all__ = ['dirs', 'files', 'iscreatable', 'iswritable', 'names']

dirs  = {}  #: The default directories
files = {}  #: The file names
names = {}  #: The aliases of names

def iswritable(path, uid=getuid(), gid=getgroups()):
  """
     Indicates if path is writable (by this process).

     @param path: The path to check
     @type path: C{str}
     @param uid: The uid of the user to check for (default: current)
     @type uid: C{int}
     @param gid: The gids of the user to check for (default: current)
     @type gid: C{[int]}
     @return: If path is writable
     @rtype: C{bool}
  """
  from os import stat

  try:
    st = stat(path)
  except OSError:
    return False

  if not uid:  # If we are the superuser then no need to uid and gid
    return bool(st.st_mode & ((1 << 1) | (1 << 4) | (1 << 7)))
  elif st.st_mode & (1 << 1):
    # If writable by world
    return True
  elif st.st_uid == uid and st.st_mode & (1 << 7):
    # If writable by us
    return True
  elif st.st_gid in gid and st.st_mode & (1 << 4):
    # If writable by one of our group
    return True
  else:
    return False

def iscreatable(path):
  """
     Indicates if path is writable, or at-least creatable (by this process).

     @return: If path is writable or creatable
     @rtype: C{bool}
  """
  from os.path import dirname, exists

  while path and path != '/' and not exists(path):
    # Path does not exist, try one further up the tree
    path = dirname(path)

  return iswritable(path)

def init_dirs():
  """
     Initialise the local directories.
  """
  from os.path import isdir, join
  from os import mkdir
  from user import home

  # The home directory for pypkg
  dirs['home'] = join(home, '.pypkg')  # ${HOME}/.pypkg

  # The database dirs
  root_dbdir = '/var/db/pypkg'
  if not getuid():
    dirs['db']      = root_dbdir # {DB_ROOT}
    dirs['db_root'] = dirs['db'] # ${DB}
  else:
    dirs['db']      = join(home, 'cache') # ${PYPKG}/db
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
