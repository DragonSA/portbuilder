"""
The Make module.  This module provides an interface to `make'.
"""

env = {}  #: The environment flags to pass to make, aka -D...

def make_target(origin, targets=None, args=[]):
  """
     Run make to build a target with the given arguments and the appropriate
     addition settings

     @param origin: The port for which to run make
     @type origin: C{str}
     @param targets: The targets to build
     @type targets: C{str} or C{(str)}
     @param args: Additional arguments for make
     @type args: C{(str)}
     @return: The make process interface
     @rtype: C{Popen}
  """
  from ports import ports_dir
  from subprocess import Popen, PIPE, STDOUT

  args = args + ["%s=%s" % (k, v) for k, v in env.iteritems()]
  if type(targets) == str:
    targets = [targets]
  elif targets == None:
    targets = []
  make = Popen(['make', '-C', ports_dir + origin] + targets + args,
               stdout=PIPE, stderr=STDOUT)

  return make