"""Environment variables, to track the state of libpb and the ports."""

from __future__ import absolute_import

import os

__all__ = [
        "CPUS", "CONFIG", "DEPEND", "MODE", "PKG_MGMT", "STAGE", "TARGET",
        "env", "env_master", "flags",
    ]

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
#               package   - package the port
#               clean     - clean the port, may be specified before and/or
#                       after the install/package target indicating that the
#                       port should cleaned before or after, respectively.
CONFIG   = ("none", "changed", "newer", "all")
DEPEND   = ("build", "package", "repo")
MODE     = ("install", "recursive", "clean")
PKG_MGMT = ("pkg", "pkgng")
STAGE    = (0, 1, 2, 3)
TARGET   = ("clean", "install", "package")
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
  "pkg_mgmt"    : "pkg",                # The package system used ('pkg(ng)?')
  "stage"       : 0,                    # The minimum level for build
  "target"      : ["install", "clean"]  # Dependency target (aka DEPENDS_TARGET)
}
