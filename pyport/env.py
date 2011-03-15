"""Environment variables."""

from os import sysconf as _sysconf

__all__ = ["cpus", "env", "env_master"]

cpus = _sysconf("SC_NPROCESSORS_ONLN")

PKG_DBDIR = "/var/db/pkg"
PORTSDIR = "/usr/ports"

env = {
"PKG_DBDIR" : PKG_DBDIR,
"PORTSDIR"  : PORTSDIR
}

env_master = {}
env_master.update(env)

def _check():
  from os import environ

  for i in env:
    if i in environ:
      env[i] = environ[i]
  # TODO: set env_master from make -V ...
_check()
