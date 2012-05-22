"""
The next generation package management tools (i.e. pkgng)..
"""
from __future__ import absolute_import

import os

__all__ = ["add", "info", "remove"]

shell_pkg_add = """
if [ ! -d %(wrkdir)s ]; then
    mkdir -p %(wrkdir)s;
    clean_wrkdir="YES";
fi;
tar -xf %(pkgfile)s -C %(wrkdir)s -s ",/.*/,,g" "*/pkg-static";
%(wrkdir)s/pkg-static add %(pkgfile)s;
rm -f %(wrkdir)s/pkg-static;
if [ "$clean_wrkdir" = "YES" ]; then
    rmdir %(wrkdir)s || true;
fi
"""

os.environ["ASSUME_ALWAYS_YES"] = "YES"

def add(port, repo=False, pkg_dir=None):
    """Add a package for port."""
    if port.attr["pkgname"].rsplit('-', 1)[0] == "pkg":
        # Special case when adding the `pkg' as it provides the functionality
        # and thus cannot add itself (or so one would thing).
        if repo or pkg_dir:
            # TODO: support installing ``pkg'' from a custom $PKGDIR
            args = False
        else:
            args = ("sh", "-ec", shell_pkg_add % port.attr)
    else:
        # Normal package add
        if repo:
            args = ("pkg", "install", "-y", port.attr["pkgname"])
        elif pkg_dir:
            pkgfile = os.path.join(pkg_dir, port.attr["pkgname"], ".txz")
            args = ("pkg", "add", pkgfile)
        else:
            args = ("pkg", "add", port.attr["pkgfile"])
    return args


def info():
    """List all installed packages with their respective port origin."""
    return ("pkg", "info", "-ao")


def query(port, prop, repo=False):
    """Query q property of a package."""
    args = ("pkg", "rquery" if repo else "query", "-F", port.attr["pkgname"])
    if prop == "config":
        args += ("%O",)
    else:
        assert not "unknown package property '%s'" % prop
    return args


def remove(pkgs):
    """Remove a package from port."""
    return ("pkg", "delete", "-y") + pkgs
