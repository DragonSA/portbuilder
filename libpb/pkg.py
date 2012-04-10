"""
The pkg module.  This module provides an interface to the system's packaging
tools.
"""
from __future__ import absolute_import

from . import env, make

__all__ = ["add"]

def add(port):
    """Add a package from port."""
    if env.flags["chroot"]:
        args = ("pkg_add", "-C", env.flags["chroot"], port.attr["pkgfile"])
    else:
        args = ("pkg_add", port.attr["pkgfile"])

    if env.flags["no_op"]:
        pkg_add = make.PopenNone(args, self)
    else:
        logfile = open(self.log_file, "a")
        pkg_add = make.Popen(args, self, stdin=subprocess.PIPE, stdout=logfile,
                             stderr=logfile)
        pkg_add.stdin.close()
    return pkg_add
