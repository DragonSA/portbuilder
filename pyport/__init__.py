"""FreeBSD port building infrastructure."""

from .env import cpus as _cpus
from .queue import QueueManager as _QueueManager

__all__ = ["attr_queue", "config_queue"]

attr_queue = _QueueManager(_cpus * 2)
config_queue = _QueueManager(max(2, _cpus * 2))
checksum_queue = _QueueManager(1)
fetch_queue = _QueueManager(1)
build_queue = _QueueManager(_cpus * 2)
install_queue = _QueueManager(1)
