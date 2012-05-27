"""Job handling for queue managers."""

from __future__ import absolute_import

from abc import abstractmethod, ABCMeta

from .signal import Signal, SignalProperty

__all__ = ["Job", "PortJob", "StalledJob"]


class StalledJob(RuntimeError):
    """Exception indicating the job cannot run right now."""
    pass


class Job(Signal):
    """Handles queued jobs with callbacks, prioritising and load management."""

    __metaclass__ = ABCMeta

    started = SignalProperty("Job.started")

    def __init__(self, load=1, priority=0):
        """Initiate a job with a given priority and load.

        Higher the value of priority, the greater the precedent.  Load
        indicates how many resources is required to run the job (i.e. CPUs)."""
        Signal.__init__(self)
        if priority is not None:
            self.priority = priority
        self.load = load
        self.pid = None
        self.__manager = None

    def __lt__(self, other):
        return self.priority > other.priority

    @abstractmethod
    def work(self):
        """Do the hard work.

        This method should be subclassed so as to do something useful."""
        pass

    def run(self, manager=None):
        """Run the job.

        The method may throw StalledJob, indicating the job should be placed on
        the stalled queue and another run in its place."""
        self.__manager = manager
        self.work()
        self.started.emit(self)

    def done(self):
        """Utility method to indicate the work has completed."""
        self.pid = None
        if self.__manager:
            self.__manager.done(self)
        self.emit(self)


class AttrJob(Job):
    """A port attributes job."""

    def __init__(self, attr):
        Job.__init__(self)
        self.attr = attr

    def __repr__(self):
        return "<AttrJob(origin=%s)>" % self.attr.origin

    def work(self):
        """Fetch a ports attributes."""
        self.pid = self.attr.get().connect(self._done).pid

    def _done(self, _make):
        """Callback special function with origin and attributes."""
        self.done()


class CleanJob(Job):
    """Clean a port job."""

    def __init__(self, port, force=False):
        Job.__init__(self)
        self.port = port
        self.pid = None
        self.status = None
        self.force = force

    def __repr__(self):
        return "<CleanJob(%s)>" % self.port

    def work(self):
        """Clean a port."""
        make = self.port.clean(self.force)
        if isinstance(make, bool) or make is not None:
            self.done()
            self.status = bool(make)
        else:
            make.connect(self._cleaned)
            self.pid = make.pid

    def _cleaned(self, make):
        """Mark job as finished."""
        from .make import SUCCESS
        self.status = make.wait() == SUCCESS
        self.done()
