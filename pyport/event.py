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

  def __len__(self):
    return len(self._events)

  def post_event(self, func, *args, **kwargs):
    """Add an event to be called asynchroniously."""
    if not callable(func):
      assert(len(func) == 3)
      self._events.append(func)
    else:
      self._events.append((func, args, kwargs))

  def run(self):
    """Run the currently queued events."""
    while len(self._events):
      func, args, kwargs = self._events.popleft()
      try:
        func(*args, **kwargs)
      except BaseException:
        raise

_manager = EventManager()

pending_events = _manager.__len__
post_event = _manager.post_event
run = _manager.run
