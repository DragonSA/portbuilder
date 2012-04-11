"""Manages jobs."""

from __future__ import absolute_import

import bisect

from .env import CPUS

__all__ = [
        "QueueManager", "queues", "attr", "config", "checksum", "fetch",
        "build", "install"
    ]


class QueueManager(object):
    """Manages jobs and runs them as resources come available."""

    def __init__(self, load=1):
        """Initialise the manager with an indication of load available."""
        self._load = load
        self._sort = False
        self.queue = []
        self.active = []
        self.stalled = []
        self.active_load = 0

    def __len__(self):
        return len(self.queue) + len(self.active) + len(self.stalled)

    @property
    def load(self):
        """Returns the current allowed load."""
        return self._load

    @load.setter
    def load(self, load):
        """Set the load and start jobs as required."""
        run = load > self._load
        self._load = load
        if run:
            self._run()

    def add(self, job):
        """Add a job to be run."""
        assert(job not in self.queue)
        if self._sort:
            self.queue.append(job)
        else:
            bisect.insort(self.queue, job)
        if self.active_load < self._load:
            self._run()

    def done(self, job):
        """Indicates a job has completed."""
        self.active.remove(job)
        self.active_load -= job.load
        if self.active_load < self._load:
            self._run()

    def reorder(self):
        """Reorder the queued jobs as their priority may have changed."""
        self._sort = True

    def remove(self, job):
        """Remove a job from being run."""
        try:
            self.queue.remove(job)
        except ValueError:
            return False
        return True

    def _run(self):
        """Fills up the remaining load with jobs"""
        from .job import StalledJob
        assert(self.active_load < self._load)

        stalled = []
        if self._sort:
            self._sort = False
            self.stalled.sort()
            self.queue.sort()
        for queue in (self.stalled, self.queue):
            while self.active_load < self._load and len(queue):
                job = self._find_job(self._load - self.active_load, queue)
                try:
                    self.active_load += job.load
                    self.active.append(job)
                    job.run(self)
                except StalledJob:
                    self.active_load -= job.load
                    self.active.remove(job)
                    stalled.append(job)
        if len(stalled):
            self.stalled.extend(stalled)
            self.stalled.sort()

    @staticmethod
    def _find_job(load, queue):
        """Find a job from queue that has at most load."""
        best_job = queue[0]
        best_idx = 0
        if best_job.load <= load:
            return queue.pop(0)
        for idx in range(1, len(queue)):
            job = queue[idx]
            if job.load <= load:
                return queue.pop(idx)
            if best_job.load > job.load:
                best_job = job
                best_idx = idx
        return queue.pop(best_idx)


attr  = QueueManager(CPUS * 2)
clean = QueueManager(1)

config   = QueueManager(1)
checksum = QueueManager(max(1, CPUS // 2))
fetch    = QueueManager(1)
build    = QueueManager(CPUS * 2)
install  = QueueManager(1)
package  = QueueManager(1)
queues   = (config, checksum, fetch, build, install, package, install, install)
