"""
The Make module.  This module provides an interface to `make'.
"""

from os import getenv

env = {}  #: The environment flags to pass to make, aka -D...
pre_cmd = []  #: Prepend to command

env["PORTSDIR"] = getenv("PORTSDIR", "/usr/ports/")  #: Location of ports

def make_target(origin, args, pipe=True, pre=True):
  """
     Run make to build a target with the given arguments and the appropriate
     addition settings

     @param origin: The port for which to run make
     @type origin: C{str}
     @param args: Targets and arguments for make
     @type args: C{(str)}
     @param pre: Prepend commands to be executed
     @type pre: C{bool}
     @return: The make process interface
     @rtype: C{Popen}
  """
  from os.path import join
  from subprocess import Popen, PIPE, STDOUT

  if type(args) is str:
    args = [args]
  args = args + ["%s=%s" % (k, v) for k, v in env.iteritems()
                  if (k != "PORTSDIR" or v != "/usr/ports/")]

  if pipe:
    stdout, stderr = PIPE, STDOUT
  else:
    stdout, stderr = None, None

  if pre:
    pre = pre_cmd
  else:
    pre = []

  make = Popen(pre + ['make', '-C', join(env["PORTSDIR"], origin)] + args,
               close_fds=True, stdout=stdout, stderr=stderr)

  return make
