"""Modelling of FreeBSD ports."""

from __future__ import absolute_import, with_statement

import os

from libpb import env, log, make, pkg, stacks

__all__ = ["Port"]

# TODO:
# Non-privileged mode
# remove NO_DEPENDS (currently doesn't work with pkgng)
# handle IS_INTERACTIVE


class Port(object):
    """
    A FreeBSD port class.
    """

    def __init__(self, origin, attr):
        """Initialise the port with the required information."""
        from .dependhandler import Dependent
        from ..env import flags

        self.attr = attr
        self.log_file = os.path.join(flags["log_dir"], self.attr["pkgname"])
        self.flags = set()
        self.load = attr["jobs_number"]
        self.origin = origin
        self.priority = 0
        self.stages = set((None,))
        self.stacks = dict((i, stacks.Stack(i)) for i in ("common", "build",
                                                          "package", "repo",
                                                          "tinderbox"))

        self.install_status = pkg.db.status(self)

        self.dependency = None
        self.dependent = Dependent(self)

    def __lt__(self, other):
        return self.dependent.priority > other.dependent.priority

    def __repr__(self):
        return "<Port(%s)>" % (self.origin)

    def resolved(self):
        """Indicate if the port meets it's dependents."""
        # TODO: use Dependent.RESOLV (current import issues)
        RESOLV = 1
        assert (self.dependent.status != RESOLV or
                (self.install_status > env.flags["buildstatus"] or
                    "upgrade" in self.flags))
        status = env.flags["buildstatus"]
        if "upgrade" in self.flags and status < pkg.OLDER:
            status = pkg.OLDER
        return (self.install_status > status and
                self.dependent.status == RESOLV)

    def clean(self, force=False):
        """Remove port's working director and log files."""
        if stacks.Build in self.stages or force:
            mak = make.make_target(self, "clean", NOCLEANDEPENDS=True)
            log.debug("Port.clean()", "Port '%s': full clean" % self.origin)
            return mak.connect(self._post_clean)
        else:
            self._post_clean()
            log.debug("Port.clean()", "Port '%s': quick clean" % self.origin)
            return True

    def _post_clean(self, _pmake=None):
        """Remove log file."""
        if not self.dependent.failed and os.path.isfile(self.log_file) and \
                (env.flags["mode"] == "clean" or stacks.Build in self.stages or
                 (self.dependency and self.dependency.failed)):
            os.unlink(self.log_file)
