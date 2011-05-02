"""Event management utilities.

Provides a framework for calling functions asynchroniously."""
from __future__ import absolute_import

__all__ = ["pending_events", "post_event", "pending_events" "run", "alarm",
           "event", "suspend_alarm", "resume_alarm", "traceback"]

class EventManager(object):
  """Handles Events that need to be called asynchroniously."""

  def __init__(self):
    """Initialise the event manager.

    A sleeper function is used to wake up once a new event comes available."""
    from collections import deque
    from select import kqueue

    self._events = deque()
    self._alarms = []
    self._alarm_active = True
    self._kq = kqueue()
    self._kq_events = {}
    self._selects = ({}, {}, {})
    self.traceback = ()
    self._no_tb = False

  def __len__(self):
    """The number of outstanding events."""
    return len(self._events)

  def alarm(self, callback, interval):
    """Add a function for period callback."""
    from time import time
    from .debug import get_tb
    self._alarms.append([callback, time() + interval, get_tb()])

  def event(self, obj, mode="r", clear=False):
    from select import kevent, KQ_EV_ADD, KQ_EV_ENABLE, KQ_EV_DELETE
    note = 0
    if mode == "r":
      from select import KQ_FILTER_READ
      event = (obj.fileno(), KQ_FILTER_READ)
    elif mode == "w":
      from select import KQ_FILTER_WRITE
      event = (obj.fileno(), KQ_FILTER_WRITE)
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
        self._kq.control((kevent(event[0], event[1], KQ_EV_ADD | KQ_EV_ENABLE, note),), 0)
        self._kq_events[event] = Signal()
      return self._kq_events[event]

  def suspend_alarm(self):
    """Suspend issuing of alarms."""
    self._alarm(None)
    self._alarm_active = False

  def resume_alarm(self):
    """Resume issuing of alarms."""
    self._alarm_active = True

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

    self.traceback = ()
    try:
      while True:
        while len(self._events):
          # Process outstanding alarm and selects before next event
          self._alarm()
          self._queue(0)

          func, args, kwargs, tb_slot, tb_call = self._events.popleft()
          self._construct_tb((tb_slot, "signal connect"), (tb_call, "signal caller"))
          func(*args, **kwargs)
          self._clear_tb()

        if not active_popen():
          # Die if no events or outstanding processes
          break

        self._sleep()

    finally:
      self._alarm(True)

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

  def _alarm(self, end=False):
    """Run all outstanding alarms."""
    from time import time

    if not self._alarm_active:
      return

    now = time()
    for item in reversed(self._alarms):
      if item[1] <= now or end is not False:
        try:
          self._construct_tb((item[2], "alarm connect"))
          trigger = item[0](end)
          self._clear_tb()
        except BaseException:
          if end is not True:
            self._alarms.remove(item)
            raise
          else:
            self._clear_tb()
            continue
        if trigger:
          item[1] = now + trigger
        else:
          self._alarms.remove(item)

  def _sleep(self):
    """Sleep while waiting for something to happend."""
    from time import time

    if len(self._alarms):
      sleep_intr = min(i[1] for i in self._alarms) - time()
    else:
      sleep_intr = 1

    if sleep_intr <= 0:
      self._alarm()
    else:
      self._queue(min(sleep_intr, 1))

  def _queue(self, timeout=None):
    """Run any events returned by kqueue."""
    while True:
      try:
        for event in self._kq.control(None, 10, timeout):
          event = (event.ident, event.filter)
          if event in self._kq_events:
            self._kq_events[event].emit()
        break
      except OSError:
        pass

_manager = EventManager()

alarm          = _manager.alarm
event          = _manager.event
suspend_alarm  = _manager.suspend_alarm
resume_alarm   = _manager.resume_alarm
pending_events = _manager.__len__
post_event     = _manager.post_event
run            = _manager.run
traceback      = lambda: _manager.traceback
