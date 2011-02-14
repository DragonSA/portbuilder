"""Make targets."""

from __future__ import absolute_import

__all__ = ["SUCCESS", "make_target"]

SUCCESS = 0

def kwargs2str(kwargs):
  for key, value in kwargs.items():
    if value is True:
      yield "-D%s" % key
    else:
      yield "%s=%s" % (key, value)

def make_target(callback, port, targets, pipe=None, **kwargs):
  """Build a make target and call a function when finished."""
  from os.path import join
  from subprocess import PIPE, STDOUT, Popen
  from .subprocess import add_popen

  if type(targets) is str:
    targets = (targets,)
  if type(targets) != tuple:
    targets = tuple(targets)

  PORTSDIR = "/usr/ports"
  args = ("make", "-C", join(PORTSDIR, port.origin)) + targets
  args += tuple(kwargs2str(kwargs))

  if pipe is True:
    stdin, stdout, stderr = PIPE, PIPE, STDOUT
  elif pipe is False:
    stdin, stdout, stderr = None, None, None
  else:
    stdin = PIPE
    stdout = open(port.log_file, 'a')
    stderr = stdout

  make = Popen(args, stdin=stdin, stdout=stdout, stderr=stderr, close_fds=True)
  if stdin is not None:
    make.stdin.close()

  add_popen(make, callback)

  return make
