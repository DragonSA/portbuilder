"""Stage building infrastructure."""

from __future__ import absolute_import

from abc import ABCMeta, abstractmethod

from libpb import env, event, job, log, queue, signal, stacks

__all__ = [
        "Builder", "builders", "depend_resolve",
    ]


class DependLoader(object):
    """Resolve a port as a dependency."""

    def __init__(self):
        self.ports = {}
        self.method = {}
        self.finished = set()

    def __call__(self, port):
        """Try resolve a port as a dependency."""
        assert not port.dependent.failed

        if port in self.ports:
            return self.ports[port]
        elif port in self.finished:
            sig = signal.Signal()
            event.post_event(sig.emit, port)
            return sig
        else:
            sig = signal.Signal()
            self.method[port] = env.flags["method"][0]

            for builder, method in zip((install, pkginstall, repoinstall),
                                       ("build", "package", "repo")):
                if port in builder.ports:
                    builder.add(port).connect(self._clean)
                    self.ports[port] = sig
                    self.method[port] = self._next(method)
                    break
            else:
                if not self._find_method(port):
                    self.finished.add(port)
                    event.post_event(sig.emit, port)
                else:
                    self.ports[port] = sig
            return sig

    def register(self, stagejob):
        """Register a build job as a dependency."""
        assert stagejob.port not in self.ports
        self.ports[stagejob.port] = signal.Signal()
        self.method[stagejob.port] = None
        stagejob.connect(self._clean)

    def _clean(self, stagejob):
        """Cleanup after a port has finished."""
        if stagejob.stack.failed:
            # If the port failed and there is another method to try
            if self._find_method(stagejob.port):
                return

        self.ports.pop(stagejob.port).emit(stagejob.port)
        self.finished.add(stagejob.port)

    def _find_method(self, port):
        """Find a method to resolve the port."""
        while True:
            method = self.method[port]
            if not method:
                # No method left, port failed to resolve
                del self.method[port]
                for stack in port.stacks.values():
                    if stack.failed and stack.failed is not True:
                        port.flags.add("failed")
                        break
                port.dependent.status_changed(exhausted=True)
                log.debug("DependLoader._find_method()",
                          "Port '%s': no viable resolve method found" %
                              (port.origin,))
                return False
            else:
                self.method[port] = self._next(self.method[port])
                if self._resolve(port, method):
                    log.debug("DependLoader._find_method()",
                              "Port '%s': resolving using method '%s'" %
                                  (port.origin, method))
                    return True
                else:
                    log.debug("DependLoader._find_method()",
                              "Port '%s': skipping resolve method '%s'" %
                                  (port.origin, method))


    def _resolve(self, port, method):
        """Try resolve the port using various methods."""
        if port.dependent.failed:
            return False
        if method == "build":
            if not install.stage.check(port):
                install.update.emit(install, Builder.ADDED, port)
                install.update.emit(install, Builder.SKIPPED, port)
                return False
            if "package" in env.flags["target"] or "package" in port.flags:
                # Connect to install job and give package ownership
                if package.stage.check(port):
                    package(port)
                stagejob = install.add(port)
            elif "install" in env.flags["target"]:
                stagejob = install(port)
            else:
                assert not "Unknown dependency target"
        elif method == "package":
            if not pkginstall.stage.check(port):
                pkginstall.update.emit(pkginstall, Builder.ADDED, port)
                pkginstall.update.emit(pkginstall, Builder.SKIPPED, port)
                return False
            stagejob = pkginstall(port)
        elif method == "repo":
            if not repoinstall.stage.check(port):
                repoinstall.update.emit(repoinstall, Builder.ADDED, port)
                repoinstall.update.emit(repoinstall, Builder.SKIPPED, port)
                return False
            stagejob = repoinstall(port)
        else:
            assert not "Unknown port resolve method"
        stagejob.connect(self._clean)
        return True

    @staticmethod
    def _next(method):
        """Find the next method used to resolve a dependency."""
        try:
            return env.flags["method"][env.flags["method"].index(method) + 1]
        except IndexError:
            return None


class Builder(object):
    """Common code from building stages."""

    __metaclass__ = ABCMeta

    ADDED     = 0
    QUEUED    = 1
    ACTIVE    = 2

    # Terminal (mutually exclusive) states
    FAILED    = 3  # Port failed to complete this stage
    SUCCEEDED = 4  # Port completed this stage
    SKIPPED   = 5  # Port skipped this stage (not possible to complete)
    DONE      = 6  # Port completed a terminal (originating stage)

    update = signal.SignalProperty("Builder.update")

    def __init__(self, stage, queue=None):
        """Initialise the builder."""
        self.queue = queue
        self.stage = stage
        self.cleanup = set()
        self.done = []
        self.failed = []
        self.ports = {}
        self.succeeded = []

    @abstractmethod
    def __call__(self, port):
        """Add port to this builder, where this builder is the primary builder
        for the port."""
        return self.add(port)

    @abstractmethod
    def add(self, port):
        """Add port to this builder."""
        pass


class ConfigBuilder(Builder):
    """Configure ports."""

    def __init__(self):
        """Initialise config builder."""
        Builder.__init__(self, stacks.Config, queue.config)

    def __call__(self, port):
        """Configure the given port."""
        return self.add(port)

    def __repr__(self):
        return "<ConfigBuilder()>"

    def add(self, port):
        """Add a port to be configured."""
        assert stacks.Config not in port.stages

        if port in self.ports:
            return self.ports[port]
        else:
            # Create a config stage job and add it to the queue
            stagejob = self.stage(port)
            stagejob.connect(self._cleanup)
            self.ports[port] = stagejob
            self.update.emit(self, Builder.ADDED, port)
            self.queue.add(stagejob)
            self.update.emit(self, Builder.QUEUED, port)
            return stagejob

    def _cleanup(self, stagejob):
        """Cleanup after the port was configured."""
        if stagejob.stack.failed:
            self.failed.append(stagejob.port)
            self.update.emit(self, Builder.FAILED, stagejob.port)
        else:
            self.update.emit(self, Builder.SUCCEEDED, stagejob.port)
        del self.ports[stagejob.port]


class DependBuilder(Builder):
    """Load port's dependencies."""

    def __init__(self):
        """Initialise depend builder"""
        Builder.__init__(self, stacks.Depend)

    def __call__(self, port):
        """Add a port to have its dependencies loaded."""
        return self.add(port)

    def __repr__(self):
        return "<DependBuilder()>"

    def add(self, port):
        """Add a port to have its dependencies loaded."""

        if port in self.ports:
            return self.ports[port]
        else:
            sig = signal.Signal()
            self.ports[port] = sig
            self.update.emit(self, Builder.ADDED, port)
            if self.stage.prev not in port.stages:
                builders[self.stage.prev].add(port).connect(self._add)
            else:
                self._add(port=port)
            return sig

    def _add(self, configjob=None, port=None):
        """Load a ports dependencies."""
        if configjob is not None:
            port = configjob.port
        self.update.emit(self, Builder.QUEUED, port)
        self.update.emit(self, Builder.ACTIVE, port)
        self.stage(port).connect(self._loaded).run()

    def _loaded(self, dependjob):
        """Port has finished loading dependency."""
        port = dependjob.port
        if port.dependency is not None:
            for q in queue.queues:
                q.reorder()
        if dependjob.stack.failed:
            self.failed.append(port)
            self.update.emit(self, Builder.FAILED, port)
        else:
            self.succeeded.append(port)
            self.update.emit(self, Builder.SUCCEEDED, port)
        self.ports.pop(port).emit(port)


class StageBuilder(Builder):
    """General port stage builder."""

    def __init__(self, stage, queue):
        """Initialise port stage builder."""
        Builder.__init__(self, stage, queue)

        self._pending = {}
        self._depends = {}

    def __call__(self, port):
        """Build the given port to the required stage."""
        self.cleanup.add(port)
        if self.stage.prev and port in builders[self.stage.prev].cleanup:
            # Steal primary ownership from previous stage
            builders[self.stage.prev].cleanup.remove(port)
        return self.add(port)

    def __repr__(self):
        return "<StageBuilder(%s)>" % self.stage.name

    def add(self, port):
        """Add a port to be build for this stage."""
        assert not port.dependent.failed

        if port in self.ports:
            return self.ports[port]
        else:
            # Create stage job
            stagejob = self.stage(port)
            stagejob.connect(self._cleanup)
            self.ports[port] = stagejob
            self.update.emit(self, Builder.ADDED, port)

            # Configure port then process it
            if stacks.Depend not in port.stages:
                depend.add(port).connect(self._add)
            else:
                assert port not in depend.ports
                # self._add() needs to be asynchronous to self.add()
                event.post_event(self._add, port)
            return stagejob

    def _add(self, port, pending=0):
        """Add a ports dependencies and prior stage to be built."""

        # Don't try and build a port that has already failed
        # or cannot be built
        if self.ports[port].stack.failed or port.dependency.failed:
            self.ports[port].done()
            return

        if env.flags["mode"] == "recursive":
            depends = port.dependency.get(self.stage)
        else:
            depends = port.dependency.check(self.stage)

        # Add all outstanding ports to be installed
        self._pending[port] = len(depends) + pending
        for p in depends:
            if p not in self._depends:
                self._depends[p] = set()
                depend_resolve(p).connect(self._depend_resolv)
            self._depends[p].add(port)

        # Build the previous stage if needed
        if self.stage.prev not in port.stages and self._port_check(port):
            self._pending[port] += 1
            builders[self.stage.prev].add(port).connect(self._stage_resolv)

        log.debug("StageBuilder._add()",
                  "Port '%s': added job for stage %s, waiting on %d" %
                      (port.origin, self.stage.name, self._pending[port]))

        # Build stage if port is ready
        if not self._pending[port]:
            self._port_ready(port)

    def _started(self, stagejob):
        """Emit a signal to indicate a port for this stage has become active."""
        self.update.emit(self, Builder.ACTIVE, stagejob.port)

    def _cleanup(self, stagejob):
        """Cleanup after the port has completed its stage."""
        port = stagejob.port
        log.debug("StageBuilder._cleanup()",
                  "Port '%s': completed job for stage %s" %
                      (stagejob.port.origin, self.stage.name))

        failed = stagejob.stack.failed or env.flags["mode"] == "clean"
        del self.ports[port]
        if port in self.cleanup and not env.flags["mode"] == "clean":
            self.cleanup.remove(port)
            if not failed:
                self.done.append(port)
                self.update.emit(self, Builder.DONE, port)
            if env.flags["target"][-1] == "clean":
                queue.clean.add(job.CleanJob(port))
        elif not failed:
            self.succeeded.append(port)
            self.update.emit(self, Builder.SUCCEEDED, port)
        if failed:
            self.update.emit(self, Builder.FAILED, port)

    def _depend_resolv(self, port):
        """Update dependency structures for resolved dependency."""
        if not port.dependent.failed and env.flags["mode"] != "clean":
            all_depends = ["'%s'" % i.origin for i in self._depends[port]]
            resolved_ports = ", ".join(all_depends)
            log.debug("StageBuilder._depend_resolv()",
                      "Port '%s': resolved stage %s for ports %s" %
                          (port.origin, self.stage.name, resolved_ports))
        for port in self._depends.pop(port):
            if port not in self.failed:
                if not port.dependency.failed and env.flags["mode"] != "clean":
                    self._pending[port] -= 1
                    if not self._pending[port]:
                        self._port_ready(port)
                else:
                    if not self.ports[port].stack.failed:
                        self.ports[port].stack.failed = True
                    self._port_failed(port)

    def _stage_resolv(self, stagejob):
        """Update pending structures for resolved prior stage."""
        port = stagejob.port
        if not stagejob.stack.failed and env.flags["mode"] != "clean":
            self._pending[port] -= 1
            if not self._pending[port]:
                self._port_ready(port)
        else:
            self._port_failed(stagejob.port)

    def _port_failed(self, port):
        if port not in self.failed:
            self.failed.append(port)
            del self._pending[port]
            self.ports[port].done()

    def _port_ready(self, port):
        """Add a port to the stage queue."""
        assert not self._pending[port]
        assert not self.ports[port].stack.failed or port.dependency.fail
        assert not port.dependency.check(self.stage)
        del self._pending[port]
        stagejob = self.ports[port]
        if self._port_check(port):
            if stagejob.complete():
                stagejob.run()
            else:
                log.debug("StageBuilder._port_ready()",
                        "Port '%s': queuing job for stage %s" %
                            (port.origin, self.stage.name))
                assert self.stage.prev in port.stages
                self.update.emit(self, Builder.QUEUED, port)
                stagejob.started.connect(self._started)
                self.queue.add(stagejob)
        else:
            if not self.stage.check(port):
                stagejob.run()
            else:
                stagejob.done()
                log.debug("StageBuilder._port_ready()",
                        "Port '%s': skipping stage %s" %
                            (port.origin, self.stage.name))

    def _port_check(self, port):
        """Check if the port should build this stage."""
        # The port needs to be built if:
        # 1) The port isn't "complete", and
        # 2) The port hasn't completed this stage
        # 3) It is possible for the pot to complete this stage
        return (not port.resolved() and self.stage not in port.stages and
                self.stage.check(port))


class BuildBuilder(StageBuilder):
    """Implement build stage specific handling."""

    def _add(self, port, pending=0):
        """Add a port to be built."""
        if env.flags["target"][0] == "clean" and self._port_check(port):
            pending += 1
            queue.clean.add(job.CleanJob(port, True).connect(self._port_clean))
        super(BuildBuilder, self)._add(port, pending)

    def _port_clean(self, cleanjob):
        """A port has finished cleaning."""
        if cleanjob.port not in self.failed:
            self._pending[cleanjob.port] -= 1
            if not self._pending[cleanjob.port]:
                self._port_ready(cleanjob.port)


class PackageBuilder(StageBuilder):
    """Implement Package specific checks."""

    def _port_check(self, port):
        """Check if the port should build this stage."""
        # The port needs to be built if:
        # 1) The base conditions are met, or
        # 2) The port has completed the INSTALL stage (which implies it now
        #       has a Dependent.RESOLV status).
        return (super(PackageBuilder, self)._port_check(port) or
                    self.stage.prev in port.stages)


depend_resolve = DependLoader()

builders = {
        stacks.Config:      ConfigBuilder(),
        stacks.Depend:      DependBuilder(),
        stacks.Checksum:    StageBuilder(stacks.Checksum, queue.checksum),
        stacks.Fetch:       StageBuilder(stacks.Fetch, queue.fetch),
        stacks.Build:       BuildBuilder(stacks.Build, queue.build),
        stacks.Install:     StageBuilder(stacks.Install, queue.install),
        stacks.Package:     PackageBuilder(stacks.Package, queue.package),
        stacks.PkgInstall:  StageBuilder(stacks.PkgInstall, queue.install),
        stacks.RepoConfig:  StageBuilder(stacks.RepoConfig, queue.attr),
        stacks.RepoFetch:   StageBuilder(stacks.RepoFetch, queue.fetch),
        stacks.RepoInstall: StageBuilder(stacks.RepoInstall, queue.install),
    }

# Head of stack "common"
depend = builders[stacks.Depend]

# Heads of stack "build"
install = builders[stacks.Install]
package = builders[stacks.Package]

# Head of stack "package"
pkginstall = builders[stacks.PkgInstall]

# Head of stack "repo"
repoinstall = builders[stacks.RepoInstall]
