"""
The stacks.package module.  This module contains the Stage that makes up the
"package" stack.
"""

import os

from libpb import env, log, make, pkg
from libpb.stacks import common, mutators

__all__ = []


class PkgInstall(mutators.Deinstall, mutators.Packagable, mutators.Resolves):
    """Install a port from a local package."""

    name = "pkginstall"
    prev = common.Depend
    stack = "package"

    @staticmethod
    def check(port):
        """Check if the package exists in $PKGDIR."""
        return os.path.isfile(env.flags["chroot"] + port.attr["pkgfile"])

    def _do_stage(self):   # pylint: disable-msg=E0202
        """Issue a pkg.add() to install the package from $PKGDIR."""
        log.debug("PkgInstall._do_stage()", "Port '%s': building stage %s" %
                      (self.port.origin, self.name))

        # pkg.add() should never be False for $PKGDIR installs
        self.pid = pkg.add(self.port).connect(self._post_pkg_add).pid

    def _post_pkg_add(self, pkg_add):
        """Process the result of pkg.add()."""
        status = pkg_add.wait() == make.SUCCESS
        if status:
            log.debug("PkgInstall._post_pkg_add()",
                      "Port '%s': finished stage %s" %
                        (self.port.origin, self.name))
        else:
            log.error("PkgInstall._port_pkg_add()",
                      "Port '%s': failed stage %s" %
                        (self.port.origin, self.name))
        self._finalise(status)
