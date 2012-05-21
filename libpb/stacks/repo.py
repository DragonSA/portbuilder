"""
The stacks.repo module.  This module contains the Stage that makes up the "repo"
stack.
"""

import os

from libpb import env, event, log, make, pkg
from libpb.stacks import common, mutators

__all__ = ["RepoConfig", "RepoFetch", "RepoInstall"]


class RepoConfig(mutators.Packagable):
    """Check if a repo package was built using the correct configuration."""

    name = "repoconfig"
    prev = common.Depend
    stack = "repo"

    def __init__(self, port):
        super(RepoConfig, self).__init__(port)
        self._pkgconfig = {}

    def complete(self):
        """Check if the package's configuration needs to be validated."""
        return not self.port.attr["config"] or env.flags["pkg_mgmt"] == "pkg"

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
            for opt in pkg_query.stdout.read().split(','):
                optn, optv = opt.split(':', 1)
                self._pkgconfig[optn] = optv.strip()
            args = []
            for opt in self.port.attr["options"]:
                args.append("-V")
                if self.port.attr["options"][opt][1] == "on":
                    yesno = "OUT"
                else:
                    yesno = ""
                args.append("WITH%s_%s" % (yesno, opt))
            pmake = make.make_target(self.port, args, pipe=True)
            self.pid = pmake.connect(self._post_make).pid
        else:
            self._finalise(False)

    def _post_make(self, pmake):
        """Process the make() command."""
        self.pid = None
        config = {}
        for opt, val in zip(self.port.attr["options"], pmake.readlines()):
            yesno = bool(len(val.strip()))
            if self.port.attr["options"][opt][1] == "on":
                yesno = not yesno
            config[opt] = "on" if yesno else "off"
        self._finalise(config == self._pkgconfig)


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
            self.pid = pkg_add.connect(self._post_pkg_add).pid
        else:
            # Cannot call self._finalise from within self.work() ->
            #   self._do_stage()
            event.post_event(self._finalise, False)

    def _post_pkg_add(self, pkg_add):
        """Process the results of pkg.add()."""
        self.pid = None
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
