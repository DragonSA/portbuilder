"""FreeBSD port building infrastructure."""

from __future__ import absolute_import

import bisect
import os

from . import event

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
            self.status = (self.pending, self.queued, self.active, self.failed,
                           (), self.done)

            self.ports = set()

            builder.update.connect(self._update)

        def __getitem__(self, status):
            """Get the ports at status"""
            return self.status[status]

        def _update(self, _builder, status, port):
            """Handle a change in the stage builder."""
            from .builder import Builder

            if status == Builder.ADDED:
                assert (port not in self.ports and port not in self.failed and
                        port not in self.done)
                if self._state.stage_started(self, port):
                    bisect.insort(self.pending, port)
                self.ports.add(port)
            elif status == Builder.QUEUED:
                self.pending.remove(port)
                bisect.insort(self.queued, port)
            elif status == Builder.ACTIVE:
                self.queued.remove(port)
                self.active.append(port)
            else:
                self.ports.remove(port)
                if port in self.active:
                    self.active.remove(port)
                elif port in self.queued:
                    self.queued.remove(port)
                else: #if port in self.pending:
                    self.pending.remove(port)
                if self.stage == port.stage:
                    if status == Builder.FAILED and port.dependent.propogate:
                        self.failed.append(port)
                    elif status == Builder.DONE:
                        self.done.append(port)
                self._state.stage_finished(self, port)

        def cleanup(self):
            """Disconnect from signals."""
            self.builder.update.disconnect(self._update)

    def __init__(self):
        """Initialise the StateTracker."""
        from .builder import builders, depend_builder

        self.stages = []
        for builder in builders:
            self.stages.append(StateTracker.Stage(builder, self))

        self._resort = False
        depend_builder.update.connect(self._sort)

    def __del__(self):
        """Disconnect from signals."""
        from .builder import depend_builder
        for i in self.stages:
            i.cleanup()
        depend_builder.update.disconnect(self._sort)

    def __getitem__(self, stage):
        """Get the Stage object for stage."""
        if isinstance(stage, slice):
            stop = stage.stop - 1
            if stage.start is not None:
                start = stage.start - 1
            else:
                start = None
            stage = slice(start, stop, stage.step)
            return self.stages[stage]
        else:
            return self.stages[stage - 1]

    def sort(self):
        """Do any sorting required for the various stages."""
        if self._resort:
            for stage in self.stages:
                stage.pending.sort()
                stage.queued.sort()
            self._resort = False

    def stage_started(self, stage, port):
        """Indicate if the stage is the currently primary for port."""
        stage_no = stage.stage
        for stage in self.stages[:stage_no - 1]:
            if port in stage.ports:
                return False
        for stage in self.stages[stage_no:]:
            if port in stage.ports:
                stage.pending.remove(port)
                break
        return True

    def stage_finished(self, stage, port):
        """Transfer primary stage to the next stage handler."""
        for stage in self.stages[stage.stage:]:
            if port in stage.ports:
                assert (port not in stage.pending and port not in stage.done and
                        port not in stage.failed)
                if self._resort:
                    stage.pending.append(port)
                else:
                    bisect.insort(stage.pending, port)
                break

    def _sort(self, _builder, status, _port):
        """Handle changes that require a resort (due to changes in priority)"""
        from .builder import Builder
        if status in (Builder.FAILED, Builder.SUCCEEDED, Builder.DONE):
            self._resort = True


def stop(kill=False, kill_clean=False):
    """Stop building ports and cleanup."""
    from .builder import builders
    from .env import CPUS, flags
    from .queue import attr_queue, clean_queue, queues
    import signal

    if flags["no_op"]:
        raise SystemExit(254)

    flags["mode"] = "clean"

    kill_queues = (attr_queue,) + queues
    if kill_clean:
        kill_queues += (clean_queue,)

    # Kill all active jobs
    for queue in kill_queues:
        for pid in (job.pid for job in queue.active if job.pid):
            try:
                if kill:
                    os.killpg(pid, signal.SIGKILL)
                else:
                    os.killpg(pid, signal.SIGTERM)
            except OSError:
                pass

    # Stop all queues
    attr_queue.load = 0
    for queue in queues:
        queue.load = 0

    # Make cleaning go a bit faster
    if kill_clean:
        clean_queue.load = 0
        return
    else:
        clean_queue.load = CPUS

    # Wait for all active ports to finish so that they may be cleaned
    active = set()
    for queue in queues:
        for job in queue.active:
            port = job.port
            active.add(port)
            port.stage_completed.connect(lambda x: x.clean())

    # Clean all other outstanding ports
    for builder in builders:
        for port in builder.ports:
            if port not in active:
                port.clean()


state = StateTracker()
