"""FreeBSD Ports."""

from __future__ import absolute_import

__all__ = ["get_port"]

class PortCache(object):
  """Caches created ports."""

  def __init__(self):
    """Initialise port cache."""
    self._ports = {}
    self._waiters = {}

  def __len__(self):
    return len(self._ports)

  def get_port(self, origin, callback):
    """Get a port and callback with it."""
    if origin in self._ports:
      from ..event import post_event
      post_event(callback, self._ports[origin])
    else:
      if origin in self._waiters:
        self._waiters[origin].append(callback)
      else:
        from .mk import attr
        self._waiters[origin] = [callback]
        attr(origin, self._attr)

  def _attr(self, origin, attr):
    """Use attr to create a port."""
    from ..event import post_event
    from .port import Port

    waiters = self._waiters.pop(origin)
    if attr is None:
      port = origin
    else:
      port = Port(origin, attr)
    self._ports[origin] = port
    for callback in waiters:
      post_event(callback, port)

_cache = PortCache()

ports = _cache.__len__
get_port = _cache.get_port
