"""FreeBSD Ports."""

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
      port = None
    else:
      port = Port(origin, attr)
      port.stage_completed.connect(self._refresh_queues)
    self._ports[origin] = port
    for callback in waiters:
      post_event(callback, port)

  def _refresh_queues(self, port):
    from ..queue import config_queue, checksum_queue, fetch_queue, build_queue, install_queue
    port.stage_completed.disconnect(self._refresh_queues)
    if port.dependancy is not None:
      for queue in (config_queue, checksum_queue, fetch_queue, build_queue, install_queue):
        queue.reorder()

_cache = PortCache()

ports = _cache.__len__
get_port = _cache.get_port
