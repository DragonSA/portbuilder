"""Environment variables."""

from __future__ import absolute_import

from os import sysconf as _sysconf
from .port.port import Port as _P

__all__ = ["cpus", "env", "env_master", "flags"]

cpus = _sysconf("SC_NPROCESSORS_ONLN")

PKG_DBDIR = "/var/db/pkg"
PORTSDIR = "/usr/ports"

env = {
  "PKG_DBDIR" : PKG_DBDIR,  # Package database directory
  "PORTSDIR"  : PORTSDIR,   # Ports directory
}

flags = {
  "chroot"      : "",                   # Chroot directory of system
  "config"      : "changed",            # Configure ports based on criteria
  "debug"       : False,                # Print extra debug messages
  "depend"      : ["build"],            # Resolve dependencies methods
  "fetch_only"  : False,                # Only fetch ports
  "log_dir"     : "/tmp/portbuilder",   # Directory for logging information
  "log_file"    : "portbuilder",        # General log file
  "mode"        : "install",            # Mode of operation
  "no_op"       : False,                # Do nothing
  "no_op_print" : False,                # Print commands that would have been executed
  "package"     : False,                # Package all installed ports
  "stage"       : _P.ABSENT             # The minimum level for build
}

env_master = {}
env_master.update(env)

def _sysctl(name):
  from subprocess import Popen, PIPE

  # TODO: create ctypes wrapper around sysctl(3)
  sysctl = Popen(("sysctl", "-n", name), stdout=PIPE, stderr=PIPE, close_fds=True)
  if sysctl.wait() == 0:
    return sysctl.stdout.read()[:-1]
  else:
    return ""

def _get_os_version():
  """Get the OS Version.  Based on how ports/Mk/bsd.port.mk sets OSVERSION"""
  # XXX: platform specific code
  from os.path import isfile
  from re import MULTILINE, search
  from subprocess import Popen, PIPE

  for path in ("/usr/include/sys/param.h", "/usr/src/sys/sys/param.h"):
    if isfile(path):
      break
  else:
    path = None

  if path:
    # We have a param.h
    osversion = search('^#define\s+__FreeBSD_version\s+([0-9]*).*$', open(path, "r").read(), MULTILINE)
    if osversion:
      return osversion.groups()[0]

  return _sysctl("kern.osreldate")

def _setup_env():
  """Update the env dictonary based on this programs environment flags."""
  from os import environ, getuid, uname

  for i in env:
    if i in environ:
      env[i] = environ[i]
  # TODO: set env_master from make -V and environ...

  # Cleanup some env variables
  if env["PORTSDIR"][-1] == '/':
    env["PORTSDIR"] = env["PORTSDIR"][:-1]

  # The following variables are conditionally set in ports/Mk/bsd.port.mk
  uname = uname()
  if "ARCH" not in environ:
    environ["ARCH"] = uname[4]
  if "OPSYS" not in environ:
    environ["OPSYS"] = uname[0]
  if "OSREL" not in environ:
    environ["OSREL"] = uname[2].split('-', 1)[0].split('(', 1)[0]
  if "OSVERSION" not in environ:
    environ["OSVERSION"] = _get_os_version()
  if uname[4] in ("amd64", "ia64") and "HAVE_COMPAT_IA32_KERN" not in environ:
    from subprocess import Popen, PIPE
    # TODO: create ctypes wrapper around sysctl(3)
    environ["HAVE_COMPAT_IA32_KERN"] = "YES" if _sysctl("compat.ia32.maxvmem") else ""
  if "LINUX_OSRELEASE" not in environ:
    environ["LINUX_OSRELEASE"] = _sysctl("compat.linux.osrelease")
  if "UID" not in environ:
    environ["UID"] = str(getuid())
  if "CONFIGURE_MAX_CMD_LEN" not in environ:
    environ["CONFIGURE_MAX_CMD_LEN"] = _sysctl("kern.argmax")

  # The following variables are also conditionally set in ports/Mk/bsd.port.subdir.mk
  if "_OSVERSION" not in environ:
    environ["_OSVERSION"] = uname[2]

_setup_env()
