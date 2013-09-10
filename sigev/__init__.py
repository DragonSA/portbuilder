"""
The SIGnal and EVent library.  This implements a similar design of signals and
events as done by the Qt graphical library (except all functions are slots).
"""

import abc
import inspect
import time
import Queue
import weakref

from sigev import util

__all__ = ['dispatch', 'dispatcher', 'event', 'post', 'run', 'Event']


class Signal(object):
    """Signal object for listening to, and emitting of, events."""

    def __init__(self):
        self._slots = []

    def __contains__(self, obj):
        return obj in self._slots

    def __len__(self):
        return len(self._slots)

    def connect(self, func):
        """Add 'func' as a callback function for the signal"""
        assert(callable(func))
        self._slots.append(func)
        return self

    def disconnect(self, func):
        """Remove 'func' as a callback function for the signal"""
        assert(func in self._slots)
        self._slots.remove(func)
        return self

    def emit(self, *args, **kwargs):
        """Asynchronously call all callback function with (optional) arguments"""
        for func in self._slots:
            post_event(AdaptFuncEvent(func, args, kwargs))
        return self


class SignalProperty(util.FactoryProperty):
    """Create a Signal() class property."""

    def __init__(self, signal=Signal):
        super(SignalProperty, self).__init__(signal)


class Filter(Signal):
    """Filter object for handling external events."""
    __metaclass__ = abc.ABCMeta

    def __init__(self, oneshot):
        self._fastpath = None
        self.oneshot = oneshot

    @property
    def fastpath(self):
        """Fastpath callback.

        The fastpath callback is called synchronously when the external
        event is received.
        """
        return self._fastpath

    @fastpath.setter
    def fastpath_setter(self, func):
        assert(callable(func))
        self._fastpath = func

    @abc.abstractmethod
    def __len__(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def delete(self):
        """Remove this filter"""
        raise NotImplementedError()

    @abc.abstractmethod
    def disable(self):
        """Disable events from this filter"""
        raise NotImplementedError()

    @abc.abstractmethod
    def enable(self):
        """Enable events from this filter"""
        raise NotImplementedError()

    def disconnect(self, func):
        super(Filter, self).disconnect(func)
        if not len(self):
            self.delete()

    def emit(self, *args, **kwargs):
        if self._fastpath:
            self._fastpath(*args, **kwargs)
        super(Filter, self).emit(*args, **kwargs)
        if self.oneshot:
            # Disconnect all slots after a oneshot event
            self._slots = []
        return self


class ExternalSource(object):
    """External source of events"""
    __metaclass__ = abc.ABCMeta

    def filter(self, descr, data):
        """Return a Filter() object for the external event described in `descr'

        The possible external events are:
            r - Read from a file descriptor (socket, vnode, fifo, pipe)
            w - Write to a file descriptor (socket, fifo, pipe)
            v - Vnode operations
                d - Unlick vnode (aka delete)
                w - Write to the vnode
                e - File extened
                a - Attribute changed
                l - Link count changed
                r - File renamed
                v - Access to the file revoked
            p - Monitor a process
                e - Exited
                f - Forked
                x - New process created via execve(2)
                t - Follow across fork call
            s - signal()s
            t - Periodic timer callback

        The following `descr' prefixes are defined:
            ! - Oneshot event (automatic disconnect of slots)
            + - Dispatch event
            ~ - Daemon event (not counted in event loop)
        """
        pass

    @abc.abstractmethod
    def listen(self, block=True):
        """Wait for external events.

        If `block' is true then wait indefinitely for events otherwise operate
        in poll mode."""
        raise NotImplementedError()

    @abc.abstractmethod
    def stop(self):
        """Stop and shutdown the event source"""
        raise NotImplementedError()
