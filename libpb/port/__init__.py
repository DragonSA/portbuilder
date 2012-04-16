"""FreeBSD Ports."""

from __future__ import absolute_import

from libpb import event, mk, signal

__all__ = ["get_port", "get_ports", "ports"]


class PortCache(object):
    """Caches created ports."""

    def __init__(self):
        """Initialise port cache."""
        self._ports = {}
        self._waiters = {}

    def __len__(self):
        return len(self._ports)

    def get_port(self, origin):
        """Get a port and callback with it."""
        if origin in self._ports:
            sig = signal.Signal()
            event.post_event(sig.emit, self._ports[origin])
            return sig
        else:
            if origin in self._waiters:
                return self._waiters[origin]
            else:
                sig = signal.Signal()
                self._waiters[origin] = sig
                mk.attr(origin).connect(self._attr)
                return sig

    def __iter__(self):
        return self._ports.values()

    def _attr(self, origin, attr):
        """Use attr to create a port."""
        from .port import Port

        sig = self._waiters.pop(origin)
        if attr is None:
            port = origin
        else:
            port = Port(origin, attr)
        self._ports[origin] = port
        sig.emit(port)


_cache = PortCache()

ports = _cache.__len__
get_port = _cache.get_port
get_ports = _cache.__iter__
