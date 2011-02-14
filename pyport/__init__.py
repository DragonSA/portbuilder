"""FreeBSD port building infrastructure."""

from .queue import QueueManager as _QM

__all__ = ["attr_queue", "config_queue"]

attr_queue = _QM(8)
config_queue = _QM(4)
