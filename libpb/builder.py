"""Stage building infrastructure."""

from __future__ import absolute_import

from abc import ABCMeta, abstractmethod
import os

from libpb import env

from .port.port import Port
from .signal import SignalProperty

__all__ = ["Builder", "builders", "config_builder", "checksum_builder",
           "fetch_builder", "build_builder", "install_builder",
           "package_builder", "pkginstall_builder"]


class DependLoader(object):
    """Resolve a port as a dependency."""

    def __init__(self):
        self.ports = {}
        self.method = {}
        self.finished = set()

    def __call__(self, port):
        """Try resolve a port as a dependency."""
        assert not port.failed

        if port in self.ports:
            return self.ports[port]
        elif port in self.finished:
            from .event import post_event
            from .signal import Signal

            job = Signal()
            post_event(job.emit, port)
            return job
        else:
            from .env import flags
            from .signal import Signal

            job = Signal()
            self.method[port] = flags["depend"][0]

            for builder in (install_builder, pkginstall_builder):
                if port in builder.ports:
                    builder.add(port).connect(self._clean)
                    self.ports[port] = job
                    self.method[port] = None
                    break
            else:
                if not self._find_method(port):
                    from .event import post_event
                    post_event(job.emit, port)
                else:
                    self.ports[port] = job
            return job

    def register(self, job):
        """Register a build job as a dependency."""
        from .signal import Signal

        assert job.port not in self.ports
        self.ports[job.port] = Signal()
        self.method[job.port] = None
        job.connect(self._clean)

    def _clean(self, job):
        """Cleanup after a port has finished."""
        if job.port.failed and self.method[job.port]:
            # If the port failed and there is another method to try
            if self._find_method(job.port):
                return

        self.ports.pop(job.port).emit(job.port)
        self.finished.add(job.port)

    def _find_method(self, port):
        """Find a method to resolve the port."""
        while True:
            method = self.method[port]
            if not method:
                # No method left, port failed to resolve
                del self.method[port]
                port.failed = True
                port.dependent.status_changed()
                return False
            else:
                self.method[port] = self._next(self.method[port])
                port.dependent.propogate = not self.method[port]
                if self._resolve(port, method):
                    return True

    def _resolve(self, port, method):
        """Try resolve the port using various methods."""
        from .env import flags

        if port.stage > Port.DEPEND:
            port.reset()
        elif port.failed:
            return False
        if method == "build":
            if "package" in flags["target"]:
                # Connect to install job and give package_builder ownership
                job = package_builder(port)
                if port in install_builder.ports:
                    # Use the install job if it exists otherwise use the package
                    # job.
                    job = install_builder.ports[port]
            elif "install" in flags["target"] or "reinstall" in flags["target"]:
                job = install_builder(port)
            else:
                assert not "Unknown dependency target"
        elif method == "package":
            if not os.path.isfile(flags["chroot"] + port.attr["pkgfile"]):
                pkginstall_builder.update.emit(pkginstall_builder,
                                               Builder.ADDED, port)
                pkginstall_builder.update.emit(pkginstall_builder,
                                               Builder.FAILED, port)
                return False
            job = pkginstall_builder(port)
        else:
            assert not "Unknown port resolve method"
        job.connect(self._clean)
        return True

    @staticmethod
    def _next(method):
        """Find the next method used to resolve a dependency."""
        from .env import flags

        try:
            return flags["depend"][flags["depend"].index(method) + 1]
        except IndexError:
            return None


class Builder(object):
    """Common code from building stages."""

    __metaclass__ = ABCMeta

    ADDED     = 0
    QUEUED    = 1
    ACTIVE    = 2
    FAILED    = 3
    SUCCEEDED = 4
    DONE      = 5

    update = SignalProperty("Builder.update")

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
        from .queue import config_queue
        Builder.__init__(self, Port.CONFIG, config_queue)

    def __call__(self, port):
        """Configure the given port."""
        return self.add(port)

    def __repr__(self):
        return "<ConfigBuilder()>"

    def add(self, port):
        """Add a port to be configured."""
        assert port.stage < Port.CONFIG

        if port in self.ports:
            return self.ports[port]
        else:
            from .job import PortJob

            # Create a config stage job and add it to the queue
            job = PortJob(port, Port.CONFIG)
            job.connect(self._cleanup)
            self.ports[port] = job
            self.update.emit(self, Builder.ADDED, port)
            self.queue.add(job)
            self.update.emit(self, Builder.QUEUED, port)
            return job

    def _cleanup(self, job):
        """Cleanup after the port was configured."""
        if job.port.failed:
            self.failed.append(job.port)
            self.update.emit(self, Builder.FAILED, job.port)
        else:
            self.update.emit(self, Builder.SUCCEEDED, job.port)
        del self.ports[job.port]


class DependBuilder(Builder):
    """Load port's dependencies."""

    def __init__(self):
        """Initialise depend builder"""
        Builder.__init__(self, Port.DEPEND)

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
            from .signal import Signal

            sig = Signal()
            self.ports[port] = sig
            self.update.emit(self, Builder.ADDED, port)
            if port.stage < Port.CONFIG:
                config_builder.add(port).connect(self._add)
            else:
                self._add(port=port)
            return sig

    def _add(self, job=None, port=None):
        """Load a ports dependencies."""
        if job is not None:
            port = job.port
        self.update.emit(self, Builder.QUEUED, port)
        self.update.emit(self, Builder.ACTIVE, port)
        port.stage_completed.connect(self._loaded)
        port.build_stage(Port.DEPEND)

    def _loaded(self, port):
        """Port has finished loading dependency."""
        from .queue import queues

        port.stage_completed.disconnect(self._loaded)
        if port.dependency is not None:
            for queue in queues:
                queue.reorder()
        if port.failed:
            self.failed.append(port)
            self.update.emit(self, Builder.FAILED, port)
        else:
            self.update.emit(self, Builder.SUCCEEDED, port)
        self.ports.pop(port).emit(port)


class StageBuilder(Builder):
    """General port stage builder."""

    def __init__(self, stage, prev_builder=None):
        """Initialise port stage builder."""
        from .queue import queues

        Builder.__init__(self, stage, queues[stage - 2])

        self._pending = {}
        self._depends = {}
        self.prev_builder = prev_builder

    def __call__(self, port):
        """Build the given port to the required stage."""
        self.cleanup.add(port)
        if self.prev_builder and port in self.prev_builder.cleanup:
            # Steal primary ownership from previous stage
            self.prev_builder.cleanup.remove(port)
        return self.add(port)

    def __repr__(self):
        return "<StageBuilder(%i)>" % self.stage

    def add(self, port):
        """Add a port to be build for this stage."""
        assert not port.failed

        if port in self.ports:
            return self.ports[port]
        else:
            from .job import PortJob

            # Create stage job
            job = PortJob(port, self.stage)
            job.connect(self._cleanup)
            assert port not in self.ports
            self.ports[port] = job
            self.update.emit(self, Builder.ADDED, port)

            # Configure port then process it
            if port.stage < Port.DEPEND:
                depend_builder.add(port).connect(self._add)
            else:
                assert port not in depend_builder.ports
                self._add(port)
            return job

    def _add(self, port, pending=0):
        """Add a ports dependencies and prior stage to be built."""
        from .env import flags

        # Don't try and build a port that has already failed
        # or cannot be built
        if port.failed or port.dependency.failed:
            self.ports[port].stage_done()
            return

        depends = port.dependency.check(self.stage)

        # Add all outstanding ports to be installed
        self._pending[port] = len(depends) + pending
        for p in depends:
            if p not in self._depends:
                self._depends[p] = set()
                depend(p).connect(self._depend_resolv)
            self._depends[p].add(port)

        # Build the previous stage if needed
        if (self.prev_builder and (port.install_status <= flags["stage"] or
                                   port.force) and port.stage < self.stage - 1):
            self._pending[port] += 1
            self.prev_builder.add(port).connect(self._stage_resolv)

        # Build stage if port is ready
        if not self._pending[port]:
            self._port_ready(port)

    def _started(self, job):
        """Emit a signal to indicate a port for this stage has become active."""
        job.started.disconnect(self._started)
        self.update.emit(self, Builder.ACTIVE, job.port)

    def _cleanup(self, job):
        """Cleanup after the port has completed its stage."""
        from .env import flags

        del self.ports[job.port]
        failed = self._port_failed(job.port)
        if job.port in self.cleanup and not flags["mode"] == "clean":
            self.cleanup.remove(job.port)
            if not failed:
                self.done.append(job.port)
                self.update.emit(self, Builder.DONE, job.port)
            if env.flags["target"][-1] == "clean":
                job.port.clean()
        elif not failed:
            self.succeeded.append(job.port)
            self.update.emit(self, Builder.SUCCEEDED, job.port)
        if failed:
            self.update.emit(self, Builder.FAILED, job.port)

    def _depend_resolv(self, port):
        """Update dependency structures for resolved dependency."""
        if not self._port_failed(port):
            for port in self._depends.pop(port):
                if not self._port_failed(port):
                    self._pending[port] -= 1
                    if not self._pending[port]:
                        self._port_ready(port)

    def _stage_resolv(self, job):
        """Update pending structures for resolved prior stage."""
        if not self._port_failed(job.port):
            self._pending[job.port] -= 1
            if not self._pending[job.port]:
                self._port_ready(job.port)

    def _port_failed(self, port):
        """Handle a failing port."""
        from .env import flags

        if port in self.failed or flags["mode"] == "clean":
            return True
        elif port.failed or port.dependency.failed:
            from .event import post_event

            if not port.dependent.propogate:
                if port in self.ports:
                    del self._pending[port]
                    for depends in (d for d in self._depends.values() if port in d):
                        depends.remove(port)
                    self.ports[port].stage_done()
                return True

            if port in self._depends:
                # Inform all dependants that they have failed (because of us)
                for deps in self._depends.pop(port):
                    if ((not self.prev_builder or
                         deps not in self.prev_builder.ports) and
                        deps not in self.failed):
                        post_event(self._port_failed, deps)
            if not self.prev_builder or port not in self.prev_builder.ports:
                # We only fail at this stage if previous stage knows about
                # failure
                self.failed.append(port)
                if port in self.ports:
                    del self._pending[port]
                    self.ports[port].stage_done()
            return True
        return False

    def _port_ready(self, port):
        """Add a port to the stage queue."""
        assert not self._pending[port]
        assert not port.failed or port.dependency.fail
        assert not port.dependency.check(self.stage)
        del self._pending[port]
        if self._port_check(port):
            assert port.stage == self.stage - 1 or self.stage > Port.PACKAGE
            self.update.emit(self, Builder.QUEUED, port)
            self.ports[port].started.connect(self._started)
            self.queue.add(self.ports[port])

    def _port_check(self, port):
        """Check if the port should build this stage."""
        from .port.dependhandler import Dependent
        from .env import flags

        if port.dependent.status == Dependent.RESOLV:
            # port does not need to build
            self.ports[port].stage_done()
        elif port.install_status > flags["stage"] and not port.force:
            # port already up to date, does not need to build
            port.dependent.status_changed()
            self.ports[port].stage_done()
        elif port.stage >= self.stage:
            self.ports[port].stage_done()
        else:
            return True
        return False


class BuildBuilder(StageBuilder):
    """Implement build stage specific handling."""

    def _add(self, port, pending=0):
        """Add a port to be built."""
        if env.flags["target"][0] == "clean":
            pending += 1
        super(BuildBuilder, self)._add(port, pending)
        port.clean(force=True).connect(self._port_clean)

    def _port_clean(self, job):
        """A port has finished cleaning."""
        self._pending[job.port] -= 1
        if not self._pending[job.port]:
            self._port_ready(job.port)


class PackageBuilder(StageBuilder):
    """Implement Package specific checks."""

    def _port_check(self, port):
        """Check if the port should build this stage."""
        if port.stage < self.stage - 1:
            port.dependent.status_changed()
            self.ports[port].stage_done()
            return False
        else:
            assert port.stage == self.stage - 1
            return True


depend = DependLoader()
config_builder     = ConfigBuilder()
depend_builder     = DependBuilder()
checksum_builder   = StageBuilder(Port.CHECKSUM)
fetch_builder      = StageBuilder(Port.FETCH,   checksum_builder)
build_builder      = BuilderBuilder(Port.BUILD,   fetch_builder)
install_builder    = StageBuilder(Port.INSTALL, build_builder)
package_builder    = PackageBuilder(Port.PACKAGE, install_builder)
pkginstall_builder = StageBuilder(Port.PKGINSTALL)
builders = (config_builder, depend_builder, checksum_builder, fetch_builder,
            build_builder, install_builder, package_builder, pkginstall_builder)
