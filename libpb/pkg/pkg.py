"""
The FreeBSD base package management tools (i.e. pkg_*).
"""
from __future__ import absolute_import

import subprocess

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
    pkg_info = subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, close_fds=True)
    pkg_info.stdin.close()

    if pkg_info.wait() != 0:
        return {}
    pkgdb = {}
    for pkg_port in pkg_info.stdout.readlines():
        pkg, origin = pkg_port.split(':')
        if origin in pkgdb:
            pkgdb[origin].add(pkg)
        else:
            pkgdb[origin] = set([pkg])
    return pkgdb
