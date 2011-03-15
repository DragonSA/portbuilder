"""Event management utilities.

Provides a framework for calling functions asynchroniously."""
__all__ = ["pending_events", "post_event", "run"]

class EventManager(object):
  """Handles Events that need to be called asynchroniously."""

  def __init__(self):
    """Initialise the event manager.

    A sleeper function is used to wake up once a new event comes available."""
    from collections import deque

    self._events = deque()
    self._alarms = []

  def __len__(self):
    return len(self._events)

  def alarm(self, callback, interval):
    """Add a function for period callback."""
    from time import time
    self._alarms.append([callback, time() + interval])

  def post_event(self, func, *args, **kwargs):
    """Add an event to be called asynchroniously."""
    if not callable(func):
      assert(len(func) == 3)
      self._events.append(func)
    else:
      self._events.append((func, args, kwargs))

  def run(self):
    """Run the currently queued events."""
    from time import time, sleep
    from .subprocess import active_popen

    while True:
      while len(self._events):
        self._alarm
        func, args, kwargs = self._events.popleft()
        try:
          func(*args, **kwargs)
        except BaseException:
          raise

      if not active_popen():
        break

      try:
        sleep_intr = min(i[1] for i in self._alarms) - time()
      except ValueError:
        sleep_intr = 1

      if sleep_intr <= 0:
        self._alarm()
      else:
        sleep(min(sleep_intr, 1))

    self._alarm(True)

  def _alarm(self, end=False):
    """Run all outstanding alarms."""
    from time import time

    now = time()
    for item in reversed(self._alarms):
      if item[1] <= time or end:
        try:
          trigger = item[0](end)
        except BaseException:
          raise
        if trigger:
          item[1] = now + trigger
        else:
          self._alarms.remove(item)

_manager = EventManager()

alarm = _manager.alarm
pending_events = _manager.__len__
post_event = _manager.post_event
run = _manager.run
