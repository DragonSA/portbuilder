"""
The stacks.repo module.  This module contains the Stage that makes up the "repo"
stack.
"""

import os

from libpb import env, event, log, make, pkg
from libpb.stacks import common, mutators

__all__ = ["RepoConfig", "RepoFetch", "RepoInstall"]


class RepoConfig(mutators.MakeStage, mutators.Packagable):
    """Check if a repo package was built using the correct configuration."""

    name = "repoconfig"
    prev = common.Depend
    stack = "repo"

    def complete(self):
        """Check if the package's configuration needs to be validated."""
        return not self.port.attr["config"] or env.flags["pkg_mgmt"] == "pkg"


class RepoFetch(mutators.Packagable):
    """Fetch the repo package."""

    name = "repofetch"
    prev = RepoConfig
    stack = "repo"

    def complete(self):
        """Check if the package needs to be fetched from the repository."""
        return os.path.isfile(env.flags["chroot"] + self.port.attr["pkgfile"])


class RepoInstall(mutators.Deinstall, mutators.Packagable, mutators.Resolves):
    """Install a port from a repo package."""

    name = "repoinstall"
    prev = common.Depend
    stack = "repo"

    def _do_stage(self):  # pylint: disable-msg=E0202
        """Issue a pkg.add() to install the package from a repo."""
        log.debug("RepoInstall._do_stage()", "Port '%s': building stage %s" %
                      (self.port.origin, self.name))

        pkg_add = pkg.add(self.port, True)
        # pkg_add may be False if installing `ports-mgmt/pkg` and
        # env.flags["pkg_mgmt"] == "pkgng"
        if pkg_add:
            self.pid = pkg_add.pid
            pkg_add.connect(self._post_pkg_add)
        else:
            # Cannot call self._finalise from within self.work() ->
            #   self._do_stage()
            event.post_event(self._finalise, False)

    def _post_pkg_add(self, pkg_add):
        """Process the results of pkg.add()."""
        status = pkg_add.wait() == make.SUCCESS
        if status:
            log.debug("PepoInstall._post_pkg_add()",
                     "Port '%s': finished stage %s" %
                        (self.port.origin, self.name))
        else:
            log.error("PepoInstall._port_pkg_add()",
                      "Port '%s': failed stage %s" %
                        (self.port.origin, self.name))
        self._finalise(status)
