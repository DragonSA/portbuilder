"""Make targets."""

from __future__ import absolute_import

__all__ = ["SUCCESS", "make_target"]

SUCCESS = 0

def env2args(env):
  for key, value in env.items():
    if value is True:
      yield "-D%s" % key
    else:
      yield "%s=%s" % (key, value)

def make_target(callback, port, targets, pipe=None, **kwargs):
  """Build a make target and call a function when finished."""
  from os.path import join
  from subprocess import PIPE, STDOUT, Popen
  from .env import env as environ, env_master
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
    if env[key] == value:
      del env[key]
  args += tuple(env2args(env))

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
