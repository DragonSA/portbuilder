"""
The SIGnal and EVent library.  This implements a similar design of signals and
events as done by the Qt graphical library (except all functions are slots).
"""

import threading
import time
import Queue

__all__ = ['dispatcher', 'post', 'run', 'Event']


def dispatcher(dispatch=None):
    """Create a dispatcher for the given 'with' context"""
    if dispatch is None:
        dispatch = Dispatcher()
    return DispatchContextManager(dispatch)

class DispatchContextManager(object):
    """@contextmanager for a dispatcher"""

    def __init__(self, dispatch):
        self.dispatch = dispatch

    def __enter__(self):
        DispatchRegister().push(self.dispatch)
        return self.dispatch

    def __exit__(self, exc, value, traceback):
        reg = DispatchRegister()
        assert(reg.get() is self.dispatch)
        try:
            if exc is None:
                reg.run()
        finally:
            reg.pop()


class EventContext(object):
    """Context information about the event."""

    def __init__(self, context, time):
        self.context = context
        self.time_created = time
        self.time_dispatched = None
        self.time_duration = None


class Event(object):
    """An event"""

    def __init__(self, func, args=tuple(), kwargs=dict()):
        self.__func = func
        self.__args = args
        self.__kwargs = kwargs
        self.context = None

    def dispatch(self):
        self.__func(*self.__args, **self.__kwargs)


class Dispatcher(object):
    """Event loop for dispatching events, handling external event sources"""

    def __init__(self):
        self._context = None
        self._external = None
        self._queue = Queue.Queue()
        self._reentry = 0
        self._start = None

    @property
    def context(self):
        """
        The current event context.
        
        The event context contains information about the event.  See 
        EventContext() for more information.

        A value of None indicates no event is being run.
        """
        return self._context

    @property
    def external(self):
        """
        The external event source.

        The external event source generates events from an external environment,
        such as the operating system.  A value of None removes the external
        event source and indicates no external event source is in use.
        """
        return self._external

    @external.setter
    def external_setter(self, external):
        assert(external is None or isinstance(external, ExternalSource))
        if self._external is not None:
            self._external.stop()
        self._external = external

    @property
    def reentry(self):
        """
        The reentry value.

        The maximum number of events to run before checking for external
        events.  A value of 0 disables event reentry.

        The purpose of event reentry is to prevent external event starvation
        for deep event chains or event storms.
        """
        return self._reentry

    @reentry.setter
    def reentry_setter(self, reentry):
        assert(reentry >= 0)
        self._reentrt = reentrt

    def _time(self):
        if self._start is None:
            return 0.0
        else:
            return time.time() - self._start

    def post(self, eventorfunc, args=None, kwargs=None):
        """
        Post an event onto the main event loop.

        Events should not be posted more than once.
        """
        if args is not None or kwargs is not None:
            assert(callable(eventorfunc))
            if args is None:
                args = tuple()
            if kwargs is None:
                kwargs = dict()
            event = Event(eventorfunc, args, kwargs)
        else:
            assert(isinstance(eventorfunc, Event))
            event = eventorfunc
        event.context = EventContext(self._context, self._time())
        self._queue.put(event)

    def run(self):
        """
        Main event loop.

        Run the event loop until no events are remaining and no external events
        are outstanding.
        """
        self._context = None  # Ensure no residual context if restarting loop
        self._start = time.time()

        while not self._queue.empty():
            # Calculate reentry value
            if self._external is None or self._reentry == 0:
                reentry = float('inf')
            else:
                reentry = self._reentry
            
            # Consume events
            while reentry > 0 and not self._queue.empty():
                event = self._queue.get_nowait()
                self._context = event.context
                self._context.time_dispatched = self._time()
                try:
                    event.dispatch()
                except:
                    self._start = None
                    raise
                finally:
                    self._context.time_duration = self._time()
                    self._context.time_duration -= self._context.time_dispatched
                    self._queue.task_done()
                self._context = None
                reentry -= 1
        
            # Get events from the external source
            if self._external is not None:
                self._external.listen(self, block=self._queue.empty())


class LocalStack(threading.local):
    """Thread local stack"""

    def __init__(self, default=list()):
        super(LocalStack, self).__init__()
        self._stack = default

    def push(self, item):
        """Push item to the top of the stack"""
        self._stack.append(item)

    def get(self):
        """Return top item of the stack"""
        return self._stack[-1]

    def pop(self):
        """Remove top item of the stack"""
        return self._stack.pop()


class Singleton(type):
    def __init__(cls, name, bases, namespace):
        super(Singleton, cls).__init__(name, bases, namespace)
        cls._instance = None

    def __call__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instance


class DispatchRegister(object):
    """Register of thread specific event dispatchers with default dispatcher"""
    __metaclass__ = Singleton

    def __init__(self):
        self.stack = LocalStack([Dispatcher()])

    def push(self, dispatch):
        """Push a dispatcher to the top of the stack"""
        self.stack.push(dispatch)

    def get(self):
        """Return the current dispatcher"""
        return self.stack.get()

    def pop(self):
        """Remove a dispatcher from the top of the stack"""
        return self.stack.pop()

    def post(self, eventorfunc, args=None, kwargs=None):
        """Post event to current dispatcher"""
        self.stack.get().post(eventorfunc, args, kwargs)

    def run(self):
        """Run the current event loop"""
        self.stack.get().run()


reg = DispatchRegister()

dispatch = reg.get
post_event = reg.post
run = reg.run

del reg

