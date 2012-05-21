"""
The FreeBSD base package management tools (i.e. pkg_*).
"""
from __future__ import absolute_import

import os

from libpb import env

__all__ = ["add", "info", "remove"]

def add(port, repo=False, pkg_dir=None):
    """Add a package from port."""
    if env.flags["chroot"]:
        args = ("pkg_add", "-C", env.flags["chroot"])
    else:
        args = ("pkg_add",)
    if repo:
        args += ("-r", port.attr["pkgname"])
    elif pkg_dir:
        args += (os.path.join(pkg_dir, port.attr["pkgname"], ".tbz"))
    else:
        args += (port.attr["pkgfile"],)
    return args


def info():
    """List all installed packages with their respective port origin."""
    args = ("pkg_info", "-aoQ")
    if env.flags["chroot"]:
        args = ("chroot", env.flags["chroot"]) + args
    return args


def remove(pkgs):
    """Remove a package from port."""
    if env.flags["chroot"]:
        args = ("pkg_delete", "-C", env.flags["chroot"])
    else:
        args = ("pkg_delete",)
    return args + pkgs
