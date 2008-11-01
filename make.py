"""
The Make module.  This module provides an interface to `make'.
"""
from os import getenv

__all__ = ['clean_log', 'env', 'log_dir', 'log_files', 'make_target',
           'pre_cmd', 'SUCCESS']

env = {}  #: The environment flags to pass to make, aka -D...
pre_cmd = []  #: Prepend to command
SUCCESS = 0  #: The value returns by a program on success
log_dir = "/tmp/pypkg"  #: The directory in which to save logs

env["PORTSDIR"] = getenv("PORTSDIR", "/usr/ports/")  #: Location of ports
env["BATCH"] = None  #: Default to use batch mode
env["NOCLEANDEPENDS"] = None  #: Default to only clean ports

def log_files(origin):
  """
     Creates the log file handler for the given port.  This is for both stdout
     and stderr.

     @param origin: The ports origin
     @type origin: C{str}
     @return: The stdout and stderr file handlers
     @rtype: C{(file, file)}
  """
  from os import makedirs as mkdirs
  from os.path import isdir, join

  if not isdir(log_dir):
    mkdirs(log_dir)
  log = open(join(log_dir, origin.replace('/', '_')), 'a')
  return log, log

def clean_log(origin):
  """
     Cleans the log files for the given port.

     @param origin: The ports origin
     @type origin: C{str}
  """
  from os import unlink
  from os.path import isfile, join

  log_file = join(log_dir, origin.replace('/', '_'))
  if isfile(log_file):
    unlink(log_file)

def make_target(origin, args, pipe=None):
  """
     Run make to build a target with the given arguments and the appropriate
     addition settings

     @param origin: The port for which to run make
     @type origin: C{str}
     @param args: Targets and arguments for make
     @type args: C{(str)}
     @return: The make process interface
     @rtype: C{Popen}
  """
  from os.path import join
  from subprocess import Popen, PIPE, STDOUT

  if isinstance(args, str):
    args = [args]
  args = args + [v and '%s="%s"' % (k, v) or "-D%s" % k for k, v in env.items()
                  if (k, v) != ("PORTSDIR", "/usr/ports/") and
                    (args[0], k) != ('config', "BATCH") and
                    (k != "NOCLEANDEPENDS" or 'clean' in args)]

  if pipe is True:
    stdin, stdout, stderr = PIPE, PIPE, STDOUT
  elif pipe:
    stdin, stdout, stderr = PIPE, pipe, STDOUT
  elif pipe is False:
    stdin, stdout, stderr = None, None, None
  else:
    stdin, (stdout, stderr) = PIPE, log_files(origin)

  if pipe is False:
    from .monitor import monitor
    monitor.pause()

  make = Popen(pre_cmd + ['make', '-C', join(env["PORTSDIR"], origin)] + args,
               close_fds=True, stdin=stdin, stdout=stdout, stderr=stderr)

  if stdin:
    make.stdin.close()

  if pipe is False:
    from .monitor import monitor
    make.wait()
    monitor.resume()

  return make
