"""FreeBSD port building infrastructure."""

from multiprocessing import cpu_count as _cpu_count
from .queue import QueueManager as _QueueManager

__all__ = ["attr_queue", "config_queue"]

_cpus = _cpu_count()

attr_queue = _QueueManager(_cpus * 2)
config_queue = _QueueManager(max(2, _cpus * 2))
checksum_queue = _QueueManager(1)
fetch_queue = _QueueManager(1)
build_queue = _QueueManager(_cpus * 2)
install_queue = _QueueManager(1)
