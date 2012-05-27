"""
The FreeBSD base package management tools (i.e. pkg_*).
"""
from __future__ import absolute_import

import os

__all__ = ["add", "change", "info", "query", "remove"]

suffix = ".tbz"

def add(port, repo=False, pkg_dir=None):
    """Add a package from port."""
    if repo:
        args = ("pkg_add", "-r", port.attr["pkgname"])
    elif pkg_dir:
        args = ("pkg_add", os.path.join(pkg_dir, port.attr["pkgname"] + suffix))
    else:
        args = ("pkg_add", port.attr["pkgfile"],)
    return args

def change(_port, prop, _value):
    """Change a property of a package,"""
    if prop == "explicit":
        return False
    else:
        assert not "unknown package property '%s'" % prop


def info(repo=False):
    """List all installed packages with their respective port origin."""
    if repo:
        return False
    return ("pkg_info", "-aoQ")


def query(_port, prop, _repo=False):
    """Query a property of a package."""
    if prop == "config":
        return False
    else:
        assert not "unknown package property '%s'" % prop


def remove(pkgs):
    """Remove a package for a port."""
    return ("pkg_delete", "-f") + pkgs
