
__all__ = ["Port"]

# TODO:
# No_opt
# Non-privleged mode

# - config
# - checksum
# * fetch
# - build
# - install

class FileLock(object):
  """A file lock, excludes accessing the same files from different ports."""
  def __init__(self):
    """Initialise the locks and database of files."""
    self._files = set()

  def acquire(self, files):
    """Acquire a lock for the given files."""
    if not self._files.isdisjoint(files):
        return False
    self._files.update(files)
    return True

  def release(self, files):
    """Release a lock fir the given files."""
    assert self._files.issuperset(files)

    self._files.symmetric_difference_update(files)

  @contextmanager
  def lock(self, files):
    """Create a context manager for a lock of the given files."""
    self.acquire(files)
    try:
      yield
    finally:
      self.release(files)

class Port(object):
  """A FreeBSD port class."""

  # Installed status flags
  ABSENT  = 0
  OLDER   = 1
  CURRENT = 2
  NEWER   = 3

  # Build stage status flags
  ZERO     = 0
  CONFIG   = 1
  CHECKSUM = 2
  FETCH    = 2
  BUILD    = 3
  INSTALL  = 4
  PKGINSTALL = 5

  _checksum_lock = FileLock()
  _fetch_lock = FileLock()
  _bad_checksum = set()
  _fetched = set()
  _fetch_failed = set()

  def __init__(self, origin, attr):
    """Itialise the port with the required information."""
    from ..signal import Signal
    from .arch import status
    from .dependhandler import Dependant

    self.attr = attr
    self.failed = False
    self.load = 1
    self.origin = origin
    self.priority = 1
    self.working = False

    self.stage = Port.ZERO
    self.stage_completed = Signal()
    self.install_status = status(origin, self.atttr)

    self.dependancy = None
    self.dependant = Dependant(self)

    if not len(self.attr['option']):
      self.stage = Port.CONFIG

  def clean(self):
    """Clean the ports working directory any log file."""
    pass

  def build_stage(self, stage):
    """Build the requested stage."""
    from time import time
    from ..job import StalledJob

    if self.working or self.stage != stage - 1 or self.failed:
      return False

    self.working = time()
    try:
      status = pre_map[stage - 1]()
      if status is not None:
        self._finalise(stage - 1, status)
    except StalledJob:
      self.working = False

  def _pre_config(self):
    """Configure the ports options."""
    self._make_target("config")

  def _post_config(self, make, status):
    """Refetch attr data if ports were configured successfully."""
    if status:
      from .arch import attr

      self.attr = attr(self.origin)
      # TODO: load dependancy
    return status

  def _pre_checksum(self):
    """Check if distfiles are available."""
    from os.path import join, isfile

    distfiles = self.attr("distfiles")
    if self._fetched.issuperset(distfiles):
      self.stage = Port.FETCH
      return True
    if not self._bad_checksum.isdisjoint(distfiles):
      return True
    distdir = self.attr("distdir")
    for i in distfiles:
      if not isfile(join(distdir, i)):
        self._bad_checksum.add(i)
        return True
    if not self._checksum_lock.acquire(distfiles):
      from ..job import StalledJob
      raise StalledJob()
    else:
      self._make_target("checksum", FETCH_REGET=0)

  def _post_checksum(self, make, status):
    """Advance to build stage if checksum passed."""
    distfiles = self.attr("distfiles")
    self._fetch_lock.release(distfiles)
    if status:
      self.stage = Port.FETCH
    else:
      self._bad_checksum.update(distfiles)
    return True

  def _pre_fetch(self):
    """Fetch the ports files."""
    distfiles = self.attr("distfiles")
    if self._fetched.issuperset(distfiles):
      return True
    if self._fetch_failed.issuperset(distfiles):
      return False
    if not self._fetch_lock.acquire(distfiles):
      from ..job import StalledJob
      raise StalledJob()
    else:
      self._make_target("checksum")

  def _post_fetch(self, make, status):
    """Register fetched files if fetch succeeded."""
    distfiles = self.attr("distfiles")
    self._fetch_lock.release(distfiles)
    if status:
      self._bad_checksum.difference_update(distfiles)
      self._fetched.update(distfiles)
    else:
      self._bad_checksum.update(distfiles)
      self._fetch_failed.update(distfiles)
    return status

  def _pre_build(self):
    """Build the port."""
    # TODO: interactive port
    self._make_target(["clean","all"])

  def _post_build(self, make, status):
    return status

  def _pre_install(self):
    """Install the port."""
    if self.install_status == Port.ABSENT:
      target = "install"
    else:
      target = ("deinstall", "reinstall")
    # TODO: package
    self._make_target(target)

  def _post_install(self, make, status):
    """Update the install status."""
    if status:
      self.install_status = Port.CURRENT
    else:
      # TODO???
      self.install_status = Port.ABSENT
    return status

  def _make_target(self, targets):
    """Build the requested targets."""
    from ..make import make_target

    make_target(self._make, self.origin, targets)

  def _make(self, make):
    """Call the _post_[stage] function and finalise the stage."""
    from ..make import SUCCESS

    post_map = (self._post_config, self._post_checksum, self._post_fetch,
                self._post_build, self._post_install)
    self._finalise(self.stage, post_map[stage](make, make.wait() is SUCCESS))

  def _finalise(self, stage, status):
    """Finalise the stage."""
    if status:
      self.failed = True
    self.working = False
    self.stage = max(stage + 1, self.stage)
    self.stage_completed(stage + 1)
