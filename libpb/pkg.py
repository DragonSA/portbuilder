"""
The pkg module.  This module provides an interface to the system's packaging
tools.
"""
from __future__ import absolute_import

from libpb import env, make, port

__all__ = ["add", "version"]

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


def version(old, new):
    """Compare two package names and indicates the difference."""
    Port = port.port.Port

    old = old.rsplit('-', 1)[1]  # Name and version components of the old pkg
    new = new.rsplit('-', 1)[1]  # Name and version components of the new pkg

    if old == new:
        # The packages are the same
        return Port.CURRENT

    # Check the ports apoch
    old, new, pstatus = cmp_attr(old, new, ',')
    if pstatus:
        return Port.CURRENT + pstatus

    # Check the ports revision
    old, new, pstatus = cmp_attr(old, new, '_')
    if old == new and pstatus:
        return Port.CURRENT + pstatus

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
            return Port.CURRENT + pstatus

    # The difference between the number of version levels
    return Port.CURRENT - cmp(len(old), len(new))


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
    return (old[0], new[1], pstatus)
