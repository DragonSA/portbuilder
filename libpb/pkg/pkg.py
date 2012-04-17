"""
The FreeBSD base package management tools (i.e. pkg_*).
"""
from __future__ import absolute_import

from libpb import env

__all__ = ["add", "info"]

def add(port, repo=False):
    """Add a package from port."""
    if env.flags["chroot"]:
        args = ("pkg_add", "-C", env.flags["chroot"])
    else:
        args = ("pkg_add",)
    if repo:
        args += ("-r", port.attr["pkgname"])
    else:
        args += (port.attr["pkgfile"],)
    return args


def info():
    """List all installed packages with their respective port origin."""
    args = ("pkg_info", "-aoQ")
    if env.flags["chroot"]:
        args = ("chroot", env.flags["chroot"]) + args
    return args
