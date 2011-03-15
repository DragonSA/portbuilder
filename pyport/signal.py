"""Callback infrastructure."""

__all__ = ["Signal"]

class Signal(object):
  """Allows signals to be sent to connected slots."""

  def __init__(self, name=""):
    """Initialising the signal."""
    self._slots = []  #: The slots connected to the signal
    self._tb = {}
    self._name = name

  def __repr__(self):
    return "<Signal(%s)>" % self._name

  def connect(self, slot):
    """Connect a callback function to the signal."""
    from .env import flags

    if slot is not None:
      if flags["debug"]:
        from traceback import extract_stack
        tb = extract_stack()[:-1]
      else:
        tb = None
      self._slots.append(slot)
      self._tb[slot] =  tb
    return self

  def disconnect(self, slot):
    """Disconnect a callback function to the signal."""
    if slot not in self._slots:
      raise RuntimeError("%s: Slot is not connected: %s" %
                         (repr(self), str(slot)))
    self._slots.remove(slot)
    self._tb.pop(slot)
    return self

  def replace(self, oldslot, newslot):
    """Replace a slot with a different one (to maintain calling order)."""
    from .env import flags

    if oldslot not in self._slots:
      raise RuntimeError("%s: Slot not connected to this signal, cannot be "\
                        "replaced: %s" % (repr(self), str(oldslot)))
    if flags["debug"]:
      from traceback import extract_stack
      tb = extract_stack()[:-1]
    else:
      tb = None
    self._slots[self._slots.index(oldslot)] = newslot
    self._tb.pop(oldslot)
    self._tb[newslot] = tb
    return self

  reconnect = replace

  def slot_index(self, slot):
    """Return the calling order of the slot (starting from 0)."""
    return self._slots.index(slot)

  def has_slot(self, slot):
    """Indicates if this signal has the slot."""
    return slot in self._slots

  def __call__(self, *args, **kwargs):
    """Emit a signal."""
    from .event import post_event

    for slot in self._slots:
      post_event((slot, args, kwargs, self._tb[slot]))
