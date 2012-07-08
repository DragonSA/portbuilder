"""
The stacks.repo module.  This module contains the Stage that makes up the "repo"
stack.
"""

import os

from libpb import env, event, make, pkg
from libpb.stacks import common, mutators

__all__ = ["RepoConfig", "RepoFetch", "RepoInstall"]


class RepoConfig(mutators.Repo):
    """Check if a repo package was built using the correct configuration."""

    name = "RepoConfig"
    prev = common.Depend
    stack = "repo"

    def __init__(self, port):
        super(RepoConfig, self).__init__(port)

    def complete(self):
        """Check if the package's configuration needs to be validated."""
        return not self.port.attr["options"] or env.flags["pkg_mgmt"] == "pkg"

    def _do_stage(self):
        pkg_query = pkg.query(self.port, "config")
        if pkg_query:
            self.pid = pkg_query.connect(self._post_pkg_query).pid
        else:
            # Unable to query, assume acceptable package
            event.post_event(self._finalise, True)

    def _post_pkg_query(self, pkg_query):
        """Process the pkg.query() command and issue a make(1) command."""
        self.pid = None
        if pkg_query.wait() == make.SUCCESS:
            pkgconfig = {}
            for opt in pkg_query.stdout.readlines():
                optn, optv = opt.split()
                pkgconfig[optn] = optv
            self._finalise(self.port.attr["options"] == pkgconfig)
        else:
            self._finalise(False)


class RepoFetch(mutators.Repo):
    """Fetch the repo package."""

    name = "RepoFetch"
    prev = RepoConfig
    stack = "repo"

    def complete(self):
        """Check if the package needs to be fetched from the repository."""
        suffix = pkg.mgmt[env.flags["pkg_mgmt"]].suffix
        path = os.path.join(env.env["PKG_CACHEDIR"],
                            self.port.attr["pkgfile"] + suffix)
        return os.path.isfile(env.flags["chroot"] + path)


class RepoInstall(mutators.Deinstall, mutators.PostFetch, mutators.Repo,
                  mutators.PackageInstaller, mutators.Resolves):
    """Install a port from a repo package."""

    name = "RepoInstall"
    prev = RepoConfig
    stack = "repo"

    def _add_pkg(self):
        """Install a package from a repository."""
        return pkg.add(self.port, True)
