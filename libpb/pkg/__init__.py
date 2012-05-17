"""
The pkg module.  This module provides an interface to the system's packaging
tools.
"""
from __future__ import absolute_import

import subprocess

from libpb import env, make
from . import pkg, pkgng

# Installed status flags
ABSENT  = 0
OLDER   = 1
CURRENT = 2
NEWER   = 3

__all__ = ["add", "db", "version"]

def add(port, repo=False, pkg_dir=None):
    """Add a package for port."""
    if env.flags["pkg_mgmt"] == "pkg":
        args = pkg.add(port, repo, pkg_dir)
    elif env.flags["pkg_mgmt"] == "pkgng":
        args = pkgng.add(port, repo, pkg_dir)
    else:
        assert not "Unknown pkg_mgmt"

    if not args:
        return args
    if env.flags["no_op"]:
        pkg_add = make.PopenNone(args, port)
    else:
        logfile = open(port.log_file, "a")
        logfile.write("# %s\n" % " ".join(args))
        pkg_add = make.Popen(args, port, subprocess.PIPE, logfile, logfile)
        pkg_add.stdin.close()
    return pkg_add


def info():
    """List all installed packages with their respective port origin."""
    if env.flags["pkg_mgmt"] == "pkg":
        args = pkg.info()
    elif env.flags["pkg_mgmt"] == "pkgng":
        args = pkgng.info()
    else:
        assert not "Unknown pkg_mgmt"

    pkg_info = subprocess.Popen(args, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
    pkg_info.stdin.close()

    pkgdb = {}
    if pkg_info.wait() == 0:
        for pkg_port in pkg_info.stdout.readlines():
            pkgname, origin = pkg_port.split(':')
            origin = origin.strip()
            if origin in pkgdb:
                pkgdb[origin].add(pkgname)
            else:
                pkgdb[origin] = set((pkgname,))
    return pkgdb


def version(old, new):
    """Compare two package names and indicates the difference."""
    old = old.rsplit('-', 1)[1]  # Name and version components of the old pkg
    new = new.rsplit('-', 1)[1]  # Name and version components of the new pkg

    if old == new:
        # The packages are the same
        return CURRENT

    # Check the ports apoch
    old, new, pstatus = cmp_attr(old, new, ',')
    if pstatus:
        return CURRENT + pstatus

    # Check the ports revision
    old, new, pstatus = cmp_attr(old, new, '_')
    if old == new and pstatus:
        return CURRENT + pstatus

    # Check the ports version from left to right
    old = old.split('.')
    new = new.split('.')
    for i in range(min(len(old), len(new))):
        # Try numerical comparison, otherwise use str
        try:
            pstatus = cmp(int(old[i]), int(new[i]))
        except ValueError:
            pstatus = cmp(old[i], new[i])
        # If there is a difference in this version level
        if pstatus:
            return CURRENT + pstatus

    # The difference between the number of version levels
    return CURRENT - cmp(len(old), len(new))


def cmp_attr(old, new, sym):
    """Compare the two attributes of the port."""
    old = old.rsplit(sym, 1)  # The value of the old pkg
    new = new.rsplit(sym, 1)  # The value of the new pkg
    if len(old) > len(new):  # If old has version and new does not
        pstatus = 1
    elif len(old) < len(new): # If new has version and old does not
        pstatus = -1
    elif len(old) == len(new) == 1:  # If neither has version
        pstatus = 0
    else: #if len(old) == 2 and len(new) == 2 # Both have version
        pstatus = cmp(int(old[1]), int(new[1]))
    return (old[0], new[0], pstatus)


class PKGDB(object):
    """A package database that tracks the installed packages."""

    def __init__(self):
        super(PKGDB, self).__init__()
        self.db = {}

    def add(self, port):
        """Indicate that a port has been installed."""
        if port.origin in self.db:
            self.db[port.origin].add(port.attr['pkgname'])
        else:
            self.db[port.origin] = set([port.attr['pkgname']])

    def load(self):
        """(Re)load the package database."""
        self.db = info()

    def remove(self, port):
        """Indicate that a port has been uninstalled."""
        if port.origin in self.db:
            portname = port.attr['pkgname'].rsplit('-', 1)[0]
            pkgs = set()
            for pkgname in self.db[port.origin]:
                if pkgname.rsplit('-', 1)[0] == portname:
                    pkgs.add(pkgname)
            self.db[port.origin] -= pkgs

    def status(self, port):
        """Query the install status of a port."""
        pstatus = ABSENT
        if port.origin in self.db:
            portname = port.attr['pkgname'].rsplit('-', 1)[0]
            for pkgname in self.db[port.origin]:
                if pkgname.rsplit('-', 1)[0] == portname:
                    pstatus = max(pstatus,
                                  version(pkgname, port.attr['pkgname']))
        return pstatus

db = PKGDB()
