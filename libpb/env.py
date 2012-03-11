"""Environment variables."""

from __future__ import absolute_import

import os
import re
import subprocess

from .port.port import Port

__all__ = ["CPUS", "env", "env_master", "flags", "setup_env"]

CPUS = os.sysconf("SC_NPROCESSORS_ONLN")

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
  "no_op_print" : False,                # Print commands instead of execution
  "package"     : False,                # Package all installed ports
  "stage"       : Port.ABSENT           # The minimum level for build
  "pkg_sys"     : "pkg"                 # The package system used ('pkg(ng)?')
}

env_master = {}
env_master.update(env)


def _make_env(*env):
    """
    Retrieve the environment variables as defined in make.conf.

    If the variable is not defined in make,conf then the os.environ value is
    used if present.
    """
    make = ["make", "-f/dev/null"] + ["-V%s" % i for i in env]
    if flags["chroot"]:
        make = ["chroot", flags["chroot"]] + make
    make = subprocess.Popen(make, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, close_fds=True)
    if make.wait() == 0:
        return dict((i, j.strip()) for i, j in zip(env, make.readlines()))
    else:
        return dict((i, "") for i in env)


def _sysctl(name):
    """Retrieve the string value of a sysctlbyname(3)."""
    # TODO: create ctypes wrapper around sysctl(3)
    sysctl = subprocess.Popen(("sysctl", "-n", name), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, close_fds=True)
    if sysctl.wait() == 0:
        return sysctl.stdout.read()[:-1]
    else:
        return ""


def _get_os_version():
    """Get the OS Version.  Based on how ports/Mk/bsd.port.mk sets OSVERSION"""
    # XXX: platform specific code
    for path in (flags["chroot"] + "/usr/include/sys/param.h",
                 flags["chroot"] + "/usr/src/sys/sys/param.h"):
        if os.path.isfile(path):
            break
    else:
        path = None

    if path:
        # We have a param.h
        osversion = re.search('^#define\s+__FreeBSD_version\s+([0-9]*).*$',
                              open(path, "r").read(), re.MULTILINE)
        if osversion:
            return osversion.groups()[0]

    return _sysctl("kern.osreldate")


def setup_env():
    """Update the env dictionary based on this programs environment flags."""
    for i in env:
        if i in os.environ:
            env[i] = os.environ[i]

    make_env = _make_env("WITH_PKGNG", "PKG_DBDIR", "PORTSDIR")

    # Update env_master with predefined values from make.conf
    for k, v in make_env.values():
        if v:
            env_master[k] = v

    # Switch to using pkgng if WITH_PKGNG is present
    if make_env["WITH_PKGNG"] or "WITH_PKGNG" in env:
        flags["pkg_sys"] = "pkgng"

    # Cleanup some env variables
    if env["PORTSDIR"][-1] == '/':
        env["PORTSDIR"] = env["PORTSDIR"][:-1]

    # Variables conditionally set in ports/Mk/bsd.port.mk
    uname = os.uname()
    if "ARCH" not in os.environ:
        os.environ["ARCH"] = uname[4]
    if "OPSYS" not in os.environ:
        os.environ["OPSYS"] = uname[0]
    if "OSREL" not in os.environ:
        os.environ["OSREL"] = uname[2].split('-', 1)[0].split('(', 1)[0]
    if "OSVERSION" not in os.environ:
        os.environ["OSVERSION"] = _get_os_version()
    if (uname[4] in ("amd64", "ia64") and
        "HAVE_COMPAT_IA32_KERN" not in os.environ):
        # TODO: create ctypes wrapper around sysctl(3)
        has_compact = "YES" if _sysctl("compat.ia32.maxvmem") else ""
        os.environ["HAVE_COMPAT_IA32_KERN"] = has_compact
    if "LINUX_OSRELEASE" not in os.environ:
        os.environ["LINUX_OSRELEASE"] = _sysctl("compat.linux.osrelease")
    if "UID" not in os.environ:
        os.environ["UID"] = str(os.getuid())
    if "CONFIGURE_MAX_CMD_LEN" not in os.environ:
        os.environ["CONFIGURE_MAX_CMD_LEN"] = _sysctl("kern.argmax")

    # Variables conditionally set in ports/Mk/bsd.port.subdir.mk
    if "_OSVERSION" not in os.environ:
        os.environ["_OSVERSION"] = uname[2]
