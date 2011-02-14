"""FreeBSD port building infrastructure."""

from .queue import QueueManager as _QM

attr_queue = _QM(8)
