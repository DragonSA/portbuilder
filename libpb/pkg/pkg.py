"""
The FreeBSD base package management tools (i.e. pkg_*).
"""
from __future__ import absolute_import

from libpb import env

__all__ = ["add", "info"]

def add(port, repo=False):
    """Add a package from port."""
    if repo:
        args = ("pkg_add", "-r", port.attr["pkgname"])
    else:
        args = ("pkg_add", port.attr["pkgfile"],)
    return args


def info():
    """List all installed packages with their respective port origin."""
    return ("pkg_info", "-aoQ")
