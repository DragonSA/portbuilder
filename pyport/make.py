"""Make targets."""

from __future__ import absolute_import

__all__ = ["SUCCESS", "make_target"]

SUCCESS = 0

def env2args(env):
  """Convert environment variables into make arguments."""
  for key, value in env.items():
    if value is True:
      yield "-D%s" % key
    else:
      yield "%s=%s" % (key, value)

def make_target(callback, port, targets, pipe=None, **kwargs):
  """Build a make target and call a function when finished."""
  from os.path import join
  from os import setsid
  from subprocess import PIPE, STDOUT, Popen
  from .env import env as environ, env_master, flags
  from .subprocess import add_popen

  if type(port) is str:
    assert pipe is True
    origin = port
  else:
    origin = port.origin

  if type(targets) is str:
    targets = (targets,)
  if type(targets) != tuple:
    targets = tuple(targets)

  env = {}
  env.update(environ)
  env.update(kwargs)

  args = ("make", "-C", join(env["PORTSDIR"], origin)) + targets
  for key, value in env_master.items():
    # Remove default environment variables
    if env[key] == value:
      del env[key]
  args += tuple(env2args(env))

  if flags["chroot"]:
    args = ("chroot", flags["chroot"]) + args

  if pipe is True:
    # Give access to subprocess output
    stdin, stdout, stderr = PIPE, PIPE, STDOUT
  elif pipe is False:
    # No piping of output (i.e. interactive)
    stdin, stdout, stderr = None, None, None
  elif not flags["no_op"]:
    # Pipe output to log_file
    stdin = PIPE
    stdout = open(port.log_file, 'a')
    stderr = stdout

  if pipe is None and flags["no_op"]:
    make = PopenNone(args)
  else:
    make = Popen(args, stdin=stdin, stdout=stdout, stderr=stderr, close_fds=True, preexec_fn=setsid)
    if stdin is not None:
      make.stdin.close()

  add_popen(make, callback)

  return make

class PopenNone(object):
  """An empty replacement for Popen."""

  returncode = SUCCESS  #: Return code for the dummy processes
  pid = -1              #: PID of the dummy processes

  stdin  = None  #: Stdin stream
  stdout = None  #: Stdout stream
  stderr = None  #: Stderr stream

  def __init__(self, args):
    from .env import flags
    if flags["no_op_print"]:
      argstr = []
      for i in args:
        argstr.append(i.replace("\\", "\\\\").replace('"', '\\"').\
                        replace("'", "\\'").replace('\n', '\\\n'))
        if ' ' in i or '\t' in i or '\n' in i:
          argstr[-1] = '"%s"' % argstr[-1]
      print " ".join(argstr)

  def wait(self):
    """Simulate Popen.wait()."""
    return self.returncode
