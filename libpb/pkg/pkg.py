"""
The FreeBSD base package management tools (i.e. pkg_*).
"""
from __future__ import absolute_import

import os

__all__ = ["add", "info", "query", "remove"]

def add(port, repo=False, pkg_dir=None):
    """Add a package from port."""
    if repo:
        args = ("pkg_add", "-r", port.attr["pkgname"])
    elif pkg_dir:
        args = ("pkg_add", os.path.join(pkg_dir, port.attr["pkgname"], ".tbz"))
    else:
        args = ("pkg_add", port.attr["pkgfile"],)
    return args


def info():
    """List all installed packages with their respective port origin."""
    return ("pkg_info", "-aoQ")


def query(_port, prop, _repo=False):
    """Query q property of a package."""
    if prop == "config":
        return False
    else:
        assert not "unknown package property '%s'" % prop


def remove(pkgs):
    """Remove a package for a port."""
    return ("pkg_delete", "-f") + pkgs
