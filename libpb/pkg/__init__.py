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

__all__ = ["add", "change", "db", "query", "remove", "version"]

mgmt = {
        "pkg":   pkg,
        "pkgng": pkgng,
    }

def add(port, repo=False, pkg_dir=None):
    """Add a package for port."""
    args = mgmt[env.flags["pkg_mgmt"]].add(port, repo, pkg_dir)
    return cmd(port, args)


def change(port, prop, value):
    """Change a property of a package,"""
    args = mgmt[env.flags["pkg_mgmt"]].change(port, prop, value)
    return cmd(port, args)


def info(repo=False):
    """List all installed packages with their respective port origin."""
    args = mgmt[env.flags["pkg_mgmt"]].info(repo)

    if not args:
        return {}
    if env.flags["chroot"]:
        args = ("chroot", env.flags["chroot"]) + args

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


def query(port, prop, repo=False):
    """Query a property of a package."""
    args = mgmt[env.flags["pkg_mgmt"]].query(port, prop, repo)
    return cmd(port, args, do_op=True)


def remove(port):
    """Remove a package for a port."""
    pkgs = tuple(db.get(port))
    args = mgmt[env.flags["pkg_mgmt"]].remove(pkgs)
    return cmd(port, args)


def cmd(port, args, do_op=False):
    """Issue a mgmt command and log the command to the port's logfile."""
    if not args:
        return args
    if env.flags["chroot"]:
        args = ("chroot", env.flags["chroot"]) + args
    if env.flags["no_op"] and not do_op:
        pkg_cmd = make.PopenNone(args, port)
    else:
        logfile = open(port.log_file, "a")
        logfile.write("# %s\n" % " ".join(args))
        pkg_cmd = make.Popen(args, port, subprocess.PIPE, logfile, logfile)
        pkg_cmd.stdin.close()
    return pkg_cmd


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

    def __init__(self, repo=False):
        super(PKGDB, self).__init__()
        self.ports = {}
        self.repo = repo

    def __contains__(self, port):
        return (port.origin in self.ports and
                port.attr["pkgname"] in self.ports[port.origin])

    def add(self, port):
        """Indicate that a port has been installed."""
        if port.origin in self.ports:
            self.ports[port.origin].add(port.attr["pkgname"])
        else:
            self.ports[port.origin] = set([port.attr["pkgname"]])

    def load(self):
        """(Re)load the package database."""
        self.ports = info(self.repo)

    def remove(self, port):
        """Indicate that a port has been uninstalled."""
        if port.origin in self.ports:
            portname = port.attr["pkgname"].rsplit('-', 1)[0]
            pkgs = set()
            for pkgname in self.ports[port.origin]:
                if pkgname.rsplit('-', 1)[0] == portname:
                    pkgs.add(pkgname)
            self.ports[port.origin] -= pkgs

    def get(self, port):
        """Get a list of packages installed for a port."""
        if port.origin in self.ports:
            return self.ports[port.origin]
        else:
            return []

    def status(self, port):
        """Query the install status of a port."""
        pstatus = ABSENT
        if port.origin in self.ports:
            pstatus = OLDER
            portname = port.attr["pkgname"].rsplit('-', 1)[0]
            for pkgname in self.ports[port.origin]:
                if pkgname.rsplit('-', 1)[0] == portname:
                    pstatus = max(pstatus,
                                  version(pkgname, port.attr["pkgname"]))
        return pstatus

db = PKGDB()
repo_db = PKGDB(repo=True)
