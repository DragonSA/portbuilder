"""
The next generation package management tools (i.e. pkgng)..
"""
from __future__ import absolute_import

import subprocess

from libpb import env

__all__ = ["add", "info"]

shell_pkg_add = """
if [ ! -d %(wrkdir)s ]; then
    mkdir %(wrkdir)s;
    clean_wrkdir="YES";
fi;
tar -xf %(pkgfile)s -C %(wrkdir)s -s ",/.*/,,g" "*/pkg-static";
%(wrkdir)s/pkg-static add %(pkgfile)s;
rm -f %(wrkdir)s/pkg-static;
if [ "$clean_wrkdir" = "YES" ]; then
    rmdir %(wrkdir)s;
fi
"""

def add(port, repo=False):
    """Add a package for port."""
    if port.attr["pkgname"].rsplit('-', 1)[0] == "pkg":
        # Special case when adding the `pkg' as it provides the functionality
        # and thus cannot add itself (or so one would thing).
        if repo:
            # TODO: indicate this cannot work
            args = ("false",)
        else:
            args = ("sh", "-c", shell_pkg_add % port.attr)
    else:
        # Normal package add
        if repo:
            args = ("pkg", "install", port.attr["pkgname"])
        else:
            args = ("pkg", "add", port.attr["pkgfile"])
    if env.flags["chroot"]:
        args = ("chroot", env.flags["chroot"]) + args
    return args


def info():
    """List all installed packages with their respective port origin."""
    args = ("pkg", "info", "-aoQ")
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
