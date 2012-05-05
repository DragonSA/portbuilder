"""Dependency handling for ports."""

from __future__ import absolute_import

import collections

from .port import Port

from libpb import log

__all__ = ['Dependent', 'Dependency']


class DependHandler(object):
    """Common declarations to both Dependent and Dependency."""

    # The type of dependencies
    BUILD   = 0
    EXTRACT = 1
    FETCH   = 2
    LIB     = 3
    RUN     = 4
    PATCH   = 5
    PKG     = 6

    #: The dependencies for a given stage
    STAGE2DEPENDS = {
      Port.CONFIG:      (),
      Port.DEPEND:      (),
      Port.CHECKSUM:    (),
      Port.FETCH:       (FETCH,),
      Port.BUILD:       (EXTRACT, PATCH, LIB, BUILD, PKG),
      Port.INSTALL:     (LIB, RUN, PKG),
      Port.PACKAGE:     (LIB, RUN, PKG),
      Port.PKGINSTALL:  (LIB, RUN, PKG),
      Port.REPOINSTALL: (LIB, RUN, PKG),
    }


class Dependent(DependHandler):
    """Tracks the dependants for a Port."""

    # The dependent status
    FAILURE  = -1  #: The port failed and/or cannot resolve dependants
    UNRESOLV = 0   #: Port does not satisfy dependants
    RESOLV   = 1   #: Dependants resolved

    def __init__(self, port):
        """Initialise the databases of dependants."""
        from ..env import flags

        DependHandler.__init__(self)
        self._dependants = [[], [], [], [], [], [], []]  #: All dependants
        self.port = port  #: The port whom we handle
        self.priority = port.priority
        self.propogate = True
        if port.install_status > flags["stage"]:
            self.status = Dependent.RESOLV
            # TODO: Change to actually check if we are resolved
        else:
            self.status = Dependent.UNRESOLV

    def __repr__(self):
        return "<Dependent(port=%s)>" % self.port.origin

    def add(self, field, port, typ):
        """Add a dependent to our list."""
        if self.status == Dependent.RESOLV:
            if not self._update(field, typ):
                self.status = Dependent.UNRESOLV
                self._notify_all()

        self._dependants[typ].append((field, port))

    def get(self, stage=None):
        """Retrieve a list of dependants."""
        if stage is None:
            depends = set()
            for i in self._dependants:
                depends.update(j[1] for j in i)
        else:
            depends = set()
            for i in DependHandler.STAGE2DEPENDS[stage]:
                depends.update(j[1] for j in self._dependants[i])

        return depends

    @property
    def failed(self):
        """Shorthand for self.status() == Dependent.FAILURE."""
        return self.status == Dependent.FAILURE

    def status_changed(self):
        """Indicates that our port's status has changed."""
        from ..env import flags

        if ((self.propogate and self.port.failed) or
            (self.port.dependency and self.port.dependency.failed)):
            status = Dependent.FAILURE
            # TODO: We might have failed and yet still satisfy our dependants
        elif flags["fetch_only"]:
            status = Dependent.RESOLV
        elif self.port.install_status > flags["stage"]:
            status = Dependent.RESOLV
            if not self._verify():
                # TODO: We may satisfy some dependants, but not others,
                # If we still do not satisfy our dependants then haven't we
                # failed?
                status = Dependent.FAILURE
        else:
            status = Dependent.UNRESOLV

        if status != self.status:
            self.status = status
            self._notify_all()

    def _notify_all(self):
        """Notify all dependants that we have changed status."""
        for i in self.get():
            i.dependency.update(self)

    def _update(self, _field, typ):
        """Check if a dependent has been resolved."""
        from ..env import flags

        if flags["fetch_only"] and self.port.stage >= Port.FETCH:
            return True

        if typ == DependHandler.BUILD:
            pass
        elif typ == DependHandler.EXTRACT:
            pass
        elif typ == DependHandler.FETCH:
            pass
        elif typ == DependHandler.LIB:
            pass
        elif typ == DependHandler.RUN:
            pass
        elif typ == DependHandler.PATCH:
            pass
        elif typ == DependHandler.PKG:
            pass

        return self.port.install_status != Port.ABSENT

    def _verify(self):
        """Check that we actually satisfy all dependants."""
        for i in range(len(self._dependants)):
            for j in self._dependants[i]:
                if not self._update(j[0], i):
                    return False
        return True


class Dependency(DependHandler):
    """Tracks the dependencies for a Port."""

    def __init__(self, port, depends=None):
        """Initialise the databases of dependencies."""
        from . import get_port

        DependHandler.__init__(self)
        self._count = 0  #: The count of outstanding dependencies
        self._dependencies = [[], [], [], [], [], [], []]  #: All dependencies
        self._loading = 0  #: Number of dependencies left to load
        self._bad = 0  #: Number of bad dependencies
        self.failed = False  #: If a dependency has failed
        self.port = port  #: The port whom we handle

        if not depends:
            depends = []

        def adder(field, typ):
            """Create an adder to place resolved port on dependency list,"""
            def do_add(port):
                """Add port to dependency list."""
                self._add(port, field, typ)
            return do_add

        for i in range(len(depends)):
            for j in depends[i]:
                self._loading += 1
                get_port(j[1]).connect(adder(j[0], i))
        if not self._loading:
            from ..event import post_event
            self._update_priority()
            post_event(self.port._post_depend, True)

    def __repr__(self):
        return "<Dependency(port=%s)>" % self.port.origin

    def _add(self, port, field, typ):
        """Add a port to our dependency list."""
        self._loading -= 1

        if not isinstance(port, str):
            status = port.dependent.status
            if port not in self._dependencies[typ]:
                self._dependencies[typ].append(port)
                port.dependent.add(field, self.port, typ)

                if status != Dependent.RESOLV:
                    self._count += 1
        else:
            log.error("Dependency._add()",
                      "Port '%s': failed to load dependency '%s'" %
                          (self.port.origin, port))
            self._bad += 1


        if isinstance(port, str) or status == Dependent.FAILURE:
            if not self.failed and not self.port.dependent.failed:
                self.failed = True
                self.port.dependent.status_changed()
            else:
                self.failed = True

        if self._loading == 0:
            self._update_priority()
            self.port._post_depend(not self._bad)

    def get(self, stage=None):
        """Retrieve a list of dependencies."""
        if stage is None:
            depends = set()
            for i in self._dependencies:
                depends.update(i)
        else:
            depends = set()
            for i in DependHandler.STAGE2DEPENDS[stage]:
                depends.update(self._dependencies[i])

        return depends

    def check(self, stage):
        """Check the dependency status for a given stage."""
        # DependHandler status might change without Port's changing
        bad = set()
        for i in DependHandler.STAGE2DEPENDS[stage]:
            bad.add(j for j in self._dependencies[i] if not j.resolved())
        return bad

    def update(self, depend):
        """Called when a dependency has changed status."""
        status = depend.status
        if status == Dependent.FAILURE:
            self.failed = True
            if not self.port.dependent.failed:
                self.port.dependent.status_changed()
            delta = -1
        elif status == Dependent.RESOLV:
            delta = 1
        else: # depend.status() == DependHandler.UNRESOLV
            delta = -1

        self._count -= (delta * len([i for i in sum(self._dependencies, [])
                                             if i == depend]))
        if self._count < 0:
            self._count = 0
        if not self._count:
            # Check that we do actually have all the dependencies met
            # TODO: Remove, debug check
            for i in self.get():
                if i.dependent.status != Dependent.RESOLV:
                    self._count += 1

    def _update_priority(self):
        """Update the priority of all ports that are affected by this port,"""
        update_list = collections.deque()
        updated = set()
        update_list.extend(self.get())
        priority = self.port.dependent.priority
        while len(update_list):
            port = update_list.popleft()
            if port not in updated:
                port.dependent.priority += priority
                if port.dependency is not None:
                    update_list.extend(port.dependency.get())
                updated.add(port)
