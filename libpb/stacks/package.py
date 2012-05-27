"""
The stacks.package module.  This module contains the Stage that makes up the
"package" stack.
"""

import os

from libpb import env, log, make, pkg
from libpb.stacks import common, mutators

__all__ = []


class PkgInstall(mutators.Deinstall, mutators.Packagable, mutators.PostFetch,
                 mutators.PackageInstaller, mutators.Resolves):
    """Install a port from a local package."""

    name = "PkgInstall"
    prev = common.Depend
    stack = "package"

    @staticmethod
    def check(port):
        """Check if the package exists in $PKGDIR."""
        return os.path.isfile(env.flags["chroot"] + port.attr["pkgfile"])

    def _add_pkg(self):
        return pkg.add(self.port)
