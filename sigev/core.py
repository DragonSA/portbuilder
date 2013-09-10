"""
The core components of the SIGnal and EVent library.
"""

__all__ = [
        'dispatch', 'dispatcher', 'event', 'post', 'run', 'Event', 'FuncEvent',
        'AdaptFuncEvent'
    ]

class EventContext(object):
    """Context information about the event."""

    def __init__(self, context, time):
        self.context = context
        self.time_created = time
        self.time_dispatched = None
        self.time_duration = None


class Event(object):
    """An event"""
    ___metaclass__ = abc.ABCMeta

    def __init__(self):
        self.context = None

    @abc.abstractmethod
    def dispatch(self):
        raise NotImplementedError()


class FuncEvent(Event):
    """An event for calling functions"""
    ___metaclass__ = abc.ABCMeta

    def __init__(self, func=None, args=tuple(), kwargs=dict()):
        assert(callable(func))
        super(FuncEvent, self).__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def dispatch(self):
        self.func(*self.args, **self.kwargs)


class AdaptFuncEvent(FuncEvent):
    """An event for calling, and adapting arguments passed to, a function"""

    _argspec = weakref.WeakKeyDictionary()

    def dispatch(self):
        """Trim the `args' and `kwargs' to what is supported by `func'"""
        if self.func not in self._argspec:
            if inspect.isclass(self.func):
                ismethod = True
                if inspect.ismethod(self.func.__init__):
                    spec = inspect.getargspec(self.func.__init__)
                else:
                    spec = inspect.ArgSpec(['self'], None, None, None)
            elif inspect.ismethod(self.func.__call__):
                ismethod = True
                spec = inspect.getargspec(self.func.__call__)
            else:
                ismethod = inspect.ismethod(self.func)
                spec = inspect.getargspec(self.func)
            self._argspec[self.func] = (spec, ismethod)
        else:
            spec, ismethod = self._argspec[self.func]
        if spec.varargs:
            args = self.args
        else:
            args = self.args[:len(spec.args) - ismethod]
        if spec.keywords:
            kwargs = self.kwargs
        else:
            kwargs = dict((k, self.kwargs[k]) for k in
                    spec.args[len(args) + ismethod:] if k in self.kwargs)
        for key in spec.args[:len(args) + ismethod]:
            if key in self.kwargs:
                raise TypeError('%s() got multiple values for keyword argument '
                        '\'%s\'' % (self.__funcname(), key))
        takes = len(spec.args) - (len(spec.defaults) if spec.defaults else 0)
        given = len(args) + len(kwargs) + ismethod
        if takes > given:
            plural = '' if takes == 1 else 's'
            raise TypeError('%s() takes at least %i argument%s (%i given)' %
                    (self.__funcname(), takes, plural, given))
        self.func(*args, **kwargs)

    def __funcname(self):
        if inspect.isclass(self.func):
            return '__init__'
        elif hasattr(self.func, '__name__'):
            return self.func.__name__
        elif inspect.ismethod(self.func.__call__):
            return '__call__'
        else:
            return '<lambda>'


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
        if (args is not None or kwargs is not None or
                not isinstance(eventorfunc, Event)):
            assert(callable(eventorfunc))
            if args is None:
                args = tuple()
            if kwargs is None:
                kwargs = dict()
            event = FuncEvent(eventorfunc, args, kwargs)
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
                while len(self._external) and (reentry == 0 or
                        self._queue.empty()):
                    self._external.listen(block=self._queue.empty())

        if self._external is not None:
            self._external.stop()


class DispatchRegister(object):
    """Register of thread specific event dispatchers with default dispatcher"""
    __metaclass__ = util.Singleton

    def __init__(self):
        self.stack = util.LocalStack([Dispatcher()])

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


def dispatcher(dispatch=None):
    """Create a dispatcher for the given 'with' context"""
    if dispatch is None:
        dispatch = Dispatcher()
    return DispatchContextManager(dispatch)


reg = DispatchRegister()

dispatch = reg.get
post_event = reg.post
run = reg.run

del reg