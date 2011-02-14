"""FreeBSD Ports."""

class PortCache(object):
  """Caches created ports."""

  def __init__(self):
    """Initialise port cache."""
    self.ports = {}
    self.waiters = {}

  def get_port(self, origin, callback):
    """Get a port and callback with it."""
    if origin in self.ports:
      from ..event import post_event
      post_event(callback, self.ports[origin])
    else:
      from .mk import attr
      self.waiters.setdefault(origin, []).append(callback)
      attr(origin, self._attr)

  def _attr(self, origin, attr):
    """Use attr to create a port."""
    from ..event import post_event
    from .port import Port

    waiters = self.waiters.pop(origin)
    port = None if attr is None else Port(origin, attr)
    self.ports[origin] = port
    for callback in waiters:
      post_event(callback, port)

_cache = PortCache()

get_port = _cache.get_port
