"""
The stacks.mutators module.  This module contains mutators that modify the
behaviour of Stages.
"""

import abc
import functools

from libpb import log, make, pkg
from libpb.stacks import base

__all__ = ["Deinstall", "MakeStage", "Packagable", "Resolves"]


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
            pkg.db.remove(self.port)
            self.port.install_status = pkg.ABSENT
            self.pid = pkg.remove(self.port).connect(self.__post_pkg_remove).pid

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
        status = self._post_make(pmake.wait() == make.SUCCESS)
        self.pid = None
        if status is not None:
            self._finalise(status)


class Packagable(base.Stage):
    """A stage depending on the packagability of a port."""
    __metaclass__ = abc.ABCMeta

    @staticmethod
    def check(port):
        """Check if the port is compatible with packaging."""
        if not port.attr["no_package"]:
            # Stages that depend on packability cannot be done if NO_PACKAGE=yes
            return False
        return True


class Resolves(base.Stage):
    """A stage that resolves a port."""

    def _finalise(self, status):
        """Mark the port as resolved."""
        if status:
            pkg.db.add(self.port)
            self.port.install_status = pkg.CURRENT
            self.port.dependent.status_changed()
        super(Resolves, self)._finalise(status)
