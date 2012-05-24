"""
The stacks.mutators module.  This module contains mutators that modify the
behaviour of Stages.
"""

import abc
import functools

from libpb import env, log, make, pkg
from libpb.stacks import base

__all__ = [
        "Deinstall", "MakeStage", "Packagable", "PackageInstaller", "PostFetch",
        "Resolves"
    ]


class Deinstall(base.Stage):
    """Deinstall a port's packages before doing the stage."""
    # Subclasses are not allowed to raise a job.JobStalled() exception.

    def work(self):
        """Deinstall the port's package before continuing with the stage."""
        # HACK: overwrite the classes' self._do_stage() method with our own
        try:
            ds_orig = self._do_stage
            # Functools.partial() should be more jit friendly than lambda
            self._do_stage = functools.partial(self.__do_stage, _ds=ds_orig)
            super(Deinstall, self).work()
        finally:
            self._do_stage = ds_orig

    def __do_stage(self, _ds):
        """Issue a pkg.remove() or proceed with the stage."""
        if self.port.install_status == pkg.ABSENT:
            self._do_stage = _ds
            self._do_stage()
        else:
            self.port.install_status = pkg.ABSENT
            self.pid = pkg.remove(self.port).connect(self.__post_pkg_remove).pid
            pkg.db.remove(self.port)

    def __post_pkg_remove(self, pkg_remove):
        """Process the results from pkg.remove."""
        self.pid = None
        if pkg_remove.wait() == make.SUCCESS:
            self._do_stage()
        else:
            log.error("Deinstall.__post_pkg_remove()",
                      "Port '%s': failed to deinstall for stage %s" %
                              (self.port.origin, self.name))
            self._finalise(False)


class MakeStage(base.Stage):
    """A stage that requires a standard make(1) call."""
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def _pre_make(self):
        """Prepare and issue a make(1) command."""
        pass

    def _post_make(self, status):  # pylint: disable-msg=R0201
        """Process the result from a make(1) command."""
        return status

    def _do_stage(self):
        """Run the self._pre_make() command to issue a make.target()."""
        self._pre_make()

    def _make_target(self, targets, **kwargs):
        """Build the requested targets."""
        pmake = make.make_target(self.port, targets, **kwargs)
        self.pid = pmake.connect(self.__make).pid

    def __make(self, pmake):
        """Call the _post_[stage] function and finalise the stage."""
        self.pid = None
        status = self._post_make(pmake.wait() == make.SUCCESS)
        if status is not None:
            self._finalise(status)


class Packagable(base.Stage):
    """A stage depending on the packagability of a port."""

    @staticmethod
    def check(port):
        """Check if the port is compatible with packaging."""
        return not port.attr["no_package"]


class PackageInstaller(base.Stage):
    """Install a port from a package."""
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def _add_pkg(self):
        """Issue a pkg.add() command."""
        pass

    def _do_stage(self):  # pylint: disable-msg=E0202
        """Issue a pkg.add() to install the package from a repo."""
        log.debug("PackageInstaller._do_stage()", "Port '%s': building stage %s" %
                      (self.port.origin, self.name))


        pkg_add = self._add_pkg()
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
        if pkg_add.wait() == make.SUCCESS:
            log.debug("PackageInstaller._post_pkg_add()",
                     "Port '%s': finished stage %s" %
                        (self.port.origin, self.name))
            if "explicit" not in self.port.flags:
                pkg_change = self.pid = pkg.change(self.port, "explicit", False)
                if pkg_change:
                    self.pid = pkg_change.connect(self._post_pkg_change).pid
                    return
            self._finalise(True)
        else:
            log.error("PackageInstaller._port_pkg_add()",
                      "Port '%s': failed stage %s" %
                        (self.port.origin, self.name))
            self._finalise(False)

    def _post_pkg_change(self, _pkg_change):
        """Process the results of pkg.change()."""
        self.pid = None
        self._finalise(True)


class PostFetch(base.Stage):
    """Indicate this stage is post fetch (and complete if fetch-only)."""

    def complete(self):
        return env.flags["fetch_only"] or super(PostFetch, self).complete()


class Resolves(base.Stage):
    """A stage that resolves a port."""

    def _finalise(self, status):
        """Mark the port as resolved."""
        if status:
            pkg.db.add(self.port)
            self.port.install_status = pkg.CURRENT
            self.port.dependent.status_changed()
        super(Resolves, self)._finalise(status)
