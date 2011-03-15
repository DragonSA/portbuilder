"""Event management utilities.

Provides a framework for calling functions asynchroniously."""
__all__ = ["pending_events", "post_event", "pending_events" "run", "alarm",
           "select", "unselect", "suspend_alarm", "resume_alarm"]

class EventManager(object):
  """Handles Events that need to be called asynchroniously."""

  def __init__(self):
    """Initialise the event manager.

    A sleeper function is used to wake up once a new event comes available."""
    from collections import deque

    self._events = deque()
    self._alarms = []
    self._alarm_active = True
    self._selects = ({}, {}, {})

  def __len__(self):
    return len(self._events)

  def alarm(self, callback, interval):
    """Add a function for period callback."""
    from time import time
    self._alarms.append([callback, time() + interval])

  def select(self, callback, rlist=None, wlist=None, xlist=None):
    """Add a callback to the required file describtor."""
    for fd, cb in zip((rlist, wlist, xlist), self._selects):
      if fd:
        if fd not in cb:
          cb[fd] = []
        cb[fd].append(callback)

  def unselect(self, callback, rlist=None, wlist=None, xlist=None):
    """Remove a callback from the given file describtor."""
    for fd, cb in zip((rlist, wlist, xlist), self._selects):
      if fd:
        cb[fd].remove(callback)
        if not len(cb[fd]):
          del cb[fd]

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
      self._events.append(func + (tb,))
    else:
      self._events.append((func, args, kwargs, None, tb))

  def run(self):
    """Run the currently queued events."""
    from .subprocess import active_popen

    try:
      while True:
        while len(self._events):
          self._alarm()
          self._select()
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

        self._sleep()

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
          if end is not True:
            raise
          else:
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
      self._select(min(sleep_intr, 1))

  def _select(self, timeout=0):
    """Run any events waiting on a select."""
    from select import error, select

    if not timeout:
      for i in self._selects:
        if len(i):
          break
      else:
        return

    rlist, wlist, xlist = self._selects

    try:
      for fds, cb in zip(select(rlist, wlist, xlist, timeout), self._selects):
        for fd in fds:
          for callback in cb[fd]:
            callback()
    except error:
      pass

_manager = EventManager()

alarm          = _manager.alarm
select         = _manager.select
unselect       = _manager.unselect
suspend_alarm  = _manager.suspend_alarm
resume_alarm   = _manager.resume_alarm
pending_events = _manager.__len__
post_event     = _manager.post_event
run            = _manager.run
