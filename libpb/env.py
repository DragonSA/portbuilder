"""Environment variables, to track the state of libpb and the ports."""

from __future__ import absolute_import

import os
import re
import subprocess

from .port.port import Port

__all__ = ["CPUS", "env", "env_master", "flags", "setup_env"]

CPUS = os.sysconf("SC_NPROCESSORS_ONLN")

PKG_DBDIR = "/var/db/pkg"
PORTSDIR = "/usr/ports"

env = {}
env_master = {
  "PKG_DBDIR" : PKG_DBDIR,  # Package database directory
  "PORTSDIR"  : PORTSDIR,   # Ports directory
}

###############################################################################
# LIBPB STATE FLAGS
###############################################################################
# chroot - The chroot directory to use.  If blank then the current root
#       (i.e. /) is used.  A mixture of `chroot' and direct file inspection is
#       used when an actual chroot is specified.
#
# config - The criteria required before prompting the user with configuring a
#       port.  The currently supported options are:
#               none    - never prompt (use the currently set options)
#               changed - only prompt if the options have changed
#               newer   - only prompt if the port is newer than when the port
#                       was last configured
#               always  - always prompt
#
# debug - Collect and display extra debugging information about  when a slot
#       was connected and when a signal was emitted.  Results in slower
#       performance and higher memory usage.
#
# depend - The methods used to resolve a dependency.  Multiple methods may be
#       specified in a sequence but a method may only be used once.  Currently
#       supported methods are:
#               build   - build the dependency from a port
#               package - install the dependency from the local package
#                       repository (${PKGREPOSITORY})
#               repo    - install the dependency from a repository (TODO)
#
# fetch_only - Only fetch a port's distfiles.
#
# log_dir - Directory where the log files, of the port build, and for
#       portbuilder, are stored.
#
# log_file - The log file for portbuilder
#
# mode - The current mode of operation.  The currently supported modes are:
#               install   - act when all port's direct dependencies are resolved
#               recursive - act when all port's direct and indirect dependencies
#                       are resolved
#               clean     - only cleanup of ports are allowed (used for early
#                       program termination)
#
# no_op - Do not do anything (and behave as if the command was successful).
#
# no_op_print - When no_op is True, print the commands that would have been
#       executed.
#
# pkg_mgmt - The package management tools used.  The currently supported tools
#       are:
#               pkg     - The package tools shipped with FreeBSD base
#               pkgng   - The next generation package tools shipped with ports
#
# stage - The minimum install stage required before a port will be build.  This
#       impacts when a dependency is considered resolved.
#
# target - The dependency targets when building a port required by a dependant.
#       The currently supported targets are:
#               install   - install the port
#               reinstall - alias for install
#               package   - package the port
#               clean     - clean the port, may be specified before and/or
#                       after the install/package target indicating that the
#                       port should cleaned before or after, respectively.
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
  "pkg_mgmt"    : "pkg"                 # The package system used ('pkg(ng)?')
  "stage"       : Port.ABSENT           # The minimum level for build
  "target"      : ["install"]           # Dependency target (aka DEPENDS_TARGET)
}


def _make_env(keys):
    """
    Retrieve the environment variables as defined in make.conf.

    If the variable is not defined in make,conf then the os.environ value is
    used if present.
    """
    make = ["make", "-f/dev/null"] + ["-V%s" % i for i in keys]
    args += ["-D%s" % k if v is True else "%s=%s" % (k, v) for k, v in env.items()]

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
            # We have a param.h
            osversion = re.search('^#define\s+__FreeBSD_version\s+([0-9]*).*$',
                                open(path, "r").read(), re.MULTILINE)
            if osversion:
                return osversion.groups()[0]
    return _sysctl("kern.osreldate")


def make_env(env, *args):
    """
    Retrieve the default make flags, available either from make.conf or from
    the environment.

    This function needs to be called after flags["chroot"] has been set but
    ideally before other flags are modified.  This function should be called
    at least once.
    """
    master_keys = master_env.keys()
    make_env = _make_env(env, args + master_keys)

    # Update env_master with predefined values from make.conf
    for k, v in zip(master_keys, make_env[-len(master_keys):]):
        if k in env:
            env_master[k] = None
        elif v:
            env[k] = env_master[k] = v

    return dict((k, v) for k, v in zip(args, make_env))


def setup_env():
    """Update the env dictionary based on this programs environment flags."""
    for i in env:
        if i in os.environ:
            env[i] = os.environ[i]

    # Cleanup some env variables
    if env["PORTSDIR"][-1] == '/':
        env["PORTSDIR"] = env["PORTSDIR"][:-1]

    # Make sure environ is not polluted with make flags
    for key in ("__MKLVL__", "MAKEFLAGS", "MAKELEVEL", "MFLAGS",
                "MAKE_JOBS_FIFO"):
        try:
            del os.environ[key]
        except KeyError:
            pass

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
