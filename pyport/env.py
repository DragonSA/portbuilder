"""Environment variables."""

from os import sysconf as _sysconf

__all__ = ["cpus", "env", "env_master", "flags"]

cpus = _sysconf("SC_NPROCESSORS_ONLN")

PKG_DBDIR = "/var/db/pkg"
PORTSDIR = "/usr/ports"

env = {
  "PKG_DBDIR" : PKG_DBDIR,  # Package database directory
  "PORTSDIR"  : PORTSDIR,   # Ports directory
}

flags = {
  "config"      : "changed",     # Configure ports based on criteria
  "debug"       : False,         # Print extra debug messages
  "fetch_only"  : False,         # Only fetch ports
  "log_dir"     : "/tmp/pypkg",  # Directory for logging information
  "mode"        : "install",     # Mode of operation
  "no_op"       : False,         # Do nothing
  "no_op_print" : False,         # Print commands that would have been executed
  "package"     : False,         # Package installed ports
}

env_master = {}
env_master.update(env)

def _check():
  """Update the env dictonary based on this programs environment flags."""
  from os import environ

  for i in env:
    if i in environ:
      env[i] = environ[i]
  # TODO: set env_master from make -V ...

  if env["PORTSDIR"][-1] == '/':
    env["PORTSDIR"] = env["PORTSDIR"][:-1]
_check()
