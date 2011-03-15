"""Event management utilities.

Provides a framework for calling functions asynchroniously."""
__all__ = ["pending_events", "post_event", "pending_events" "run", "alarm",
           "suspend_alarm", "resume_alarm"]

class EventManager(object):
  """Handles Events that need to be called asynchroniously."""

  def __init__(self):
    """Initialise the event manager.

    A sleeper function is used to wake up once a new event comes available."""
    from collections import deque

    self._events = deque()
    self._alarms = []
    self._alarm_active = True

  def __len__(self):
    return len(self._events)

  def alarm(self, callback, interval):
    """Add a function for period callback."""
    from time import time
    self._alarms.append([callback, time() + interval])

  def suspend_alarm(self):
    """Suspend issuing of alarms."""
    self._alarm(None)
    self._alarm_active = False

  def resume_alarm(self):
    """Resume issuing of alarms."""
    self._alarm_active = True

  def post_event(self, func, *args, **kwargs):
    """Add an event to be called asynchroniously."""
    from .env import flags
    if flags["debug"]:
      from traceback import extract_stack
      tb = extract_stack()[:-1]
    else:
      tb = None
    if not callable(func):
      assert(len(func) == 4)
      self._events.append(func + (tb[:-1],))
    else:
      self._events.append((func, args, kwargs, None, tb))

  def run(self):
    """Run the currently queued events."""
    from time import time, sleep
    from .subprocess import active_popen

    try:
      while True:
        while len(self._events):
          self._alarm()
          func, args, kwargs, tb_slot, tb_call = self._events.popleft()
          try:
            func(*args, **kwargs)
          except BaseException:
            for tb, name in ((tb_slot, "connect"), (tb_call, "caller")):
              if tb is not None:
                from traceback import format_list
                print "Traceback from signal %s (most recent call last):" % name
                print "".join(format_list(tb))
            raise

        if not active_popen():
          break

        if len(self._alarms):
          sleep_intr = min(i[1] for i in self._alarms) - time()
        else:
          sleep_intr = 1

        if sleep_intr <= 0:
          self._alarm()
        else:
          sleep(min(sleep_intr, 1))
    finally:
      self._alarm(True)

  def _alarm(self, end=False):
    """Run all outstanding alarms."""
    from time import time

    if not self._alarm_active:
      return

    now = time()
    for item in reversed(self._alarms):
      if item[1] <= now or end is not False:
        try:
          trigger = item[0](end)
        except BaseException:
          if not end:
            raise
        if trigger:
          item[1] = now + trigger
        else:
          self._alarms.remove(item)

_manager = EventManager()

alarm          = _manager.alarm
suspend_alarm  = _manager.suspend_alarm
resume_alarm   = _manager.resume_alarm
pending_events = _manager.__len__
post_event     = _manager.post_event
run            = _manager.run
