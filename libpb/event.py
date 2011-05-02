"""Event management utilities.

Provides a framework for calling functions asynchroniously."""
from __future__ import absolute_import

from .signal import InlineSignal, SignalProperty

__all__ = ["alarm", "event", "pending_events", "post_event", "resume", "run",
           "start", "stop", "suspend", "traceback"]

class EventManager(object):
  """Handles Events that need to be called asynchroniously."""

  start = SignalProperty("start", signal=InlineSignal)
  stop  = SignalProperty("stop",  signal=InlineSignal)

  def __init__(self):
    """Initialise the event manager.

    A sleeper function is used to wake up once a new event comes available."""
    from collections import deque
    from select import kqueue

    self._events = deque()
    self._alarms = 0
    self._alarm_active = True
    self._kq = kqueue()
    self._kq_events = {}
    self.traceback = ()
    self._no_tb = False

  def __len__(self):
    """The number of outstanding events."""
    return len(self._events)

  def alarm(self):
    """Add a function for period callback."""
    self._alarms += 1
    return self._alarms

  def event(self, obj, mode="r", clear=False, data=0):
    import select
    from select import kevent, KQ_EV_ADD, KQ_EV_ENABLE, KQ_EV_DELETE
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
    elif mode.startswith("s"):
      event = (obj, select.KQ_FILTER_SIGNAL)
    else:
      raise ValueError("unknown event mode")

    if clear:
      try:
        self._kq_events.pop(event)
        self._kq.control((kevent(event[0], event[1], KQ_EV_DELETE),), 0)
      except KeyError:
        raise KeyError("no event registered")
    else:
      if event not in self._kq_events:
        from .signal import Signal
        self._kq.control((kevent(event[0], event[1], KQ_EV_ADD | KQ_EV_ENABLE, note, data),), 0)
        self._kq_events[event] = (Signal(), obj)
      return self._kq_events[event][0]

  def post_event(self, func, *args, **kwargs):
    """Add an event to be called asynchroniously."""
    from .debug import get_tb

    if not callable(func):
      assert(len(func) == 4)
      self._events.append(func + (get_tb(1),))
    else:
      self._events.append((func, args, kwargs, None, get_tb()))

  def run(self):
    """Run the currently queued events."""
    from .subprocess import active_popen

    self._no_tb = False
    self.traceback = None
    try:
      self.start.emit()
      while True:
        while len(self._events):
          func, args, kwargs, tb_slot, tb_call = self._events.popleft()
          self._construct_tb((tb_slot, "signal connect"), (tb_call, "signal caller"))
          func(*args, **kwargs)
          self._clear_tb()

        if not active_popen():
          # Die if no events or outstanding processes
          break

        self._queue()

    finally:
      self.stop.emit()

  def _construct_tb(self, *args):
    """Add extra tracebacks for debugging perposes."""
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
    from select import kevent, KQ_FILTER_PROC, KQ_NOTE_EXIT, KQ_EV_DELETE

    for ev in self._kq.control(None, 2, timeout):
      event = (ev.ident, ev.filter)
      if event in self._kq_events:
        if ev.filter == KQ_FILTER_PROC and ev.fflags == KQ_NOTE_EXIT:
          signal, obj = self._kq_events.pop(event)
        else:
          signal, obj = self._kq_events[event]
        signal.emit(obj)

_manager = EventManager()

alarm          = _manager.alarm
event          = _manager.event
pending_events = _manager.__len__
post_event     = _manager.post_event
resume         = _manager.start.emit
run            = _manager.run
start          = _manager.start
stop           = _manager.stop
suspend        = _manager.stop.emit
traceback      = lambda: (_manager.traceback if _manager.traceback else ())
