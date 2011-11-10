"""Event management utilities.

Provides a framework for calling functions asynchronously."""
from __future__ import absolute_import

import errno
import collections
import select

from .signal import InlineSignal, SignalProperty

__all__ = ["alarm", "event", "pending_events", "post_event", "resume", "run",
           "start", "stop", "suspend", "traceback"]


class EventManager(object):
    """Handles Events that need to be called asynchronously."""

    start = SignalProperty("start", signal=InlineSignal)
    stop  = SignalProperty("stop",  signal=InlineSignal)

    def __init__(self):
        """Initialise the event manager.

        A sleeper function is used to wake up once a new event comes
        available."""
        self._events = collections.deque()
        self._alarms = 0
        self._alarm_active = True
        self._kq = select.kqueue()
        self._kq_events = {}
        self.traceback = ()
        self.event_count = 0
        self._no_tb = False

    def __len__(self):
        """The number of outstanding events."""
        return len(self._events)

    def alarm(self):
        """Add a function for period callback."""
        self._alarms += 1
        return self._alarms

    def event(self, obj, mode="r", clear=False, data=0):
        """Add or remove a kevent monitor.

        Current events are:
          r - Read a file descriptor
          w - Write to a file descriptor
          t - Periodic timer callback (data=period)
          p - Monitor subprocess
            f - Inform when subprocess forks
            e - Inform when subprocess uses execve(2)
            - - Informs when subprocess dies
          s - Signal handling
        """
        note = 0
        if mode == "r":
            event = (obj.fileno(), select.KQ_FILTER_READ)
        elif mode == "w":
            event = (obj.fileno(), select.KQ_FILTER_WRITE)
        elif mode == "t":
            event = (obj, select.KQ_FILTER_TIMER)
            data = int(data * 1000)
        elif mode.startswith("p"):
            event = (obj.pid, select.KQ_FILTER_PROC)
            if "f" in mode[1:]:
                note |= select.KQ_NOTE_FORK
            elif "e" in mode[1:]:
                note |= select.KQ_NOTE_EXEC
            elif "-" in mode[1:]:
                # HACK: work around python bug!!!
                note -= select.KQ_NOTE_EXIT
        elif mode == "s":
            event = (obj, select.KQ_FILTER_SIGNAL)
        else:
            raise ValueError("unknown event mode")

        if clear:
            try:
                self._kq_events.pop(event)
                self._kq.control((select.kevent(event[0], event[1],
                                                select.KQ_EV_DELETE),), 0)
            except KeyError:
                raise KeyError("no event registered")
        else:
            if event not in self._kq_events:
                from .signal import Signal
                kevent = select.kevent(event[0], event[1],
                                       select.KQ_EV_ADD | select.KQ_EV_ENABLE,
                                       note, data)
                self._kq.control((kevent,), 0)
                self._kq_events[event] = Signal()
            return self._kq_events[event]

    def post_event(self, func, *args, **kwargs):
        """Add an event to be called asynchronously."""
        from .debug import get_tb

        if not callable(func):
            assert(len(func) == 4)
            self._events.append(func + (get_tb(1),))
        else:
            self._events.append((func, args, kwargs, None, get_tb()))

    def run(self):
        """Run the currently queued events."""
        from .queue import attr_queue, clean_queue, queues

        self._no_tb = False
        self.traceback = None
        queues = (attr_queue, clean_queue) + queues
        try:
            self.start.emit()
            while True:
                events = 0
                while len(self._events):
                    events += 1
                    if events == 50:
                        self._queue(0)
                        events = 0
                    self.event_count += 1
                    func, args, kwargs, tb_slot, tb_call = self._events.popleft()
                    self._construct_tb((tb_slot, "signal connect"),
                                       (tb_call, "signal caller"))
                    func(*args, **kwargs)
                    self._clear_tb()

                for queue in queues:
                    if len(queue.active):
                        break
                else:
                    # Die if no events or outstanding processes
                    break

                self._queue()

        finally:
            self.stop.emit()

    def _construct_tb(self, *args):
        """Add extra tracebacks for debugging purposes."""
        if self.traceback is not None:
            self._no_tb = True
            return
        self.traceback = []
        for tb, name in args:
            if tb is not None:
                self.traceback.append((tb, name))

    def _clear_tb(self):
        """Clear any pending tracebacks."""
        if self._no_tb:
            self._no_tb = False
        else:
            self.traceback = None

    def _queue(self, timeout=None):
        """Run any events returned by kqueue."""
        while True:
            # Retry self._kq_control if the system call was interrupted
            try:
                events = self._kq.control(None, 16, timeout)
                break
            except OSError, e:
                if e.errno == errno.EINTR:
                    continue
                raise
        for ev in events:
            event = (ev.ident, ev.filter)
            if event in self._kq_events:
                if (ev.filter == select.KQ_FILTER_PROC and
                    ev.fflags == select.KQ_NOTE_EXIT):
                    self._kq_events.pop(event).emit()
                else:
                    self._kq_events[event].emit()


_manager = EventManager()

alarm          = _manager.alarm
event          = _manager.event
event_count    = lambda: _manager.event_count
pending_events = _manager.__len__
post_event     = _manager.post_event
resume         = _manager.start.emit
run            = _manager.run
start          = _manager.start
stop           = _manager.stop
suspend        = _manager.stop.emit
traceback      = lambda: (_manager.traceback if _manager.traceback else ())
