"""
FreeBSD port building infrastructure.

To initialise libpb, the following functions needs to be called (in this order).
 1) libpb.mk_defaults()
 2.1) libpb.mk.clean()
 2.2) libob.mk.cache()
 2.3) libob.pkg.db.load()

(1) loads the defaults from the port infrastructure.  The calling program must
ensure that libpb.env.flags["chroot"] has been set, if valid, and that all
libpb.env.env values have been initialised.

The sub-items of (2) can be called in any order.  (2.1) cleans the environment
variables (libpb.env.env and os.environ).  (2.2) caches expensive operations
used by the ports infrastructure and is optional.  (2.3) loads the package
database.

(2.1) and (2.2) need to be called before initiating a Port object.
"""

from __future__ import absolute_import

import bisect
import collections
import os

from libpb import builder, event, queue

__all__ = ["event", "state", "stop"]


class StateTracker(object):
    """Track the state of the port builder."""

    class Stage(object):
        """Information about each stage of the build process."""

        def __init__(self, builder, state):
            """Initialise the Stage's state."""
            self.builder = builder
            self.stage = builder.stage
            self._state = state
            self.active  = []
            self.queued  = []
            self.pending = []
            self.failed  = []
            self.done    = []
            self.status = {
                    builder.ADDED:   self.pending,
                    builder.QUEUED:  self.queued,
                    builder.ACTIVE:  self.active,
                    builder.FAILED:  self.failed,
                    builder.DONE:    self.done,
                }

            self.ports = set()

            builder.update.connect(self._update)

        def __getitem__(self, status):
            """Get the ports at status"""
            return self.status[status]

        def _update(self, _builder, status, port):
            """Handle a change in the stage builder."""
            from .builder import Builder

            if status == Builder.ADDED:
                assert port not in self.ports
                assert port not in self.failed
                assert port not in self.done
                if self._state.stage_started(self, port):
                    bisect.insort(self.pending, port)
                self.ports.add(port)
            elif status == Builder.QUEUED:
                self.pending.remove(port)
                bisect.insort(self.queued, port)
            elif status == Builder.ACTIVE:
                self.queued.remove(port)
                self.active.append(port)
            else:  # status in (FAILED, SUCCEEDED, SKIPPED, DONE)
                self.ports.remove(port)
                if port in self.active:
                    self.active.remove(port)
                elif port in self.queued:
                    self.queued.remove(port)
                elif port in self.pending:
                    self.pending.remove(port)
                if self.stage in port.stages:
                    if status == Builder.FAILED:
                        self.failed.append(port)
                    elif status == Builder.DONE:
                        self.done.append(port)
                self._state.stage_finished(self, port)

        def cleanup(self):
            """Disconnect from signals."""
            self.builder.update.disconnect(self._update)

    def __init__(self):
        """Initialise the StateTracker."""
        self.stages = collections.OrderedDict()
        for b in builder.builders.values():
            self.stages[b.stage] = StateTracker.Stage(b, self)

        self._resort = False
        # Resort when the port has initialised it's dependency class.
        builder.depend.update.connect(self._sort)

    def __del__(self):
        """Disconnect from signals."""
        for i in self.stages.values():
            i.cleanup()
        builder.depend.update.disconnect(self._sort)

    def __getitem__(self, stage):
        """Get the Stage object for stage."""
        return self.stages[stage]

    def sort(self):
        """Do any sorting required for the various stages."""
        if self._resort:
            for stage in self.stages.values():
                stage.pending.sort()
                stage.queued.sort()
            self._resort = False

    def stage_started(self, stage, port):
        """Indicate if the stage is the current primary for port."""
        stages = set((stage.stage,))
        stage = stage.stage.prev
        while stage:
            if port in self.stages[stage].ports:
                return False
            stage = stage.prev
        for stage in self.stages:
            if stage.prev in stages:
                if port in self.stages[stage].ports:
                    self.stages[stage].pending.remove(port)
                else:
                    stages.add(stage)
        return True

    def stage_finished(self, stage, port):
        """Transfer primary stage to the next stage handler."""
        stages = set((stage.stage,))
        for stage in self.stages:
            if stage.prev in stages:
                if port in self.stages[stage].ports:
                    if port in self.stages[stage].failed:
                        continue
                    assert port not in self.stages[stage].pending
                    assert port not in self.stages[stage].done
                    if self._resort:
                        self.stages[stage].pending.append(port)
                    else:
                        bisect.insort(self.stages[stage].pending, port)
                else:
                    stages.add(stage)

    def _sort(self, _builder, status, _port):
        """Handle changes that require a resort (due to changes in priority)"""
        from .builder import Builder
        if status in (Builder.FAILED, Builder.SUCCEEDED):
            self._resort = True


def stop(kill=False, kill_clean=False):
    """Stop building ports and cleanup."""
    from .env import CPUS, flags
    import signal

    if flags["no_op"]:
        raise SystemExit(254)

    flags["mode"] = "clean"

    kill_queues = (queue.attr,) + queue.queues
    if kill_clean:
        kill_queues += (queue.clean,)

    # Kill all active jobs
    for q in kill_queues:
        for pid in (job.pid for job in q.active if job.pid):
            try:
                if kill:
                    os.killpg(pid, signal.SIGKILL)
                else:
                    os.killpg(pid, signal.SIGTERM)
            except OSError:
                pass

    # Stop all queues
    queue.attr.load = 0
    for q in queue.queues:
        q.load = 0

    # Make cleaning go a bit faster
    if kill_clean:
        queue.clean.load = 0
        return
    else:
        queue.clean.load = CPUS

    # Wait for all active ports to finish so that they may be cleaned
    active = set()
    for q in queue.queues:
        for job in q.active:
            active.add(job.port)
            job.connect(lambda x: x.port.clean())

    # Clean all other outstanding ports
    for b in builder.builders.values():
        for port in b.ports:
            if port not in active:
                port.clean()


state = StateTracker()
