"""Modelling of FreeBSD ports."""

from contextlib import contextmanager

__all__ = ["Port"]

# TODO:
# No_opt
# Non-privleged mode
# Package install (or separate stage)
# remove NO_DEPENDS once thoroughly tested???
# handle IS_INTERACTIVE

# - config
# * checksum
# * fetch
# * build
# - install

class Lock(object):
  """A simple Uniprocessor lock."""

  def __init__(self):
    """Initialise lock."""
    self._locked = False

  def acquire(self):
    """Acquire lock."""
    from ..event import suspend_alarm

    if self._locked:
      return False
    self._locked = True
    suspend_alarm()
    return True

  def release(self):
    """Release lock."""
    from ..event import resume_alarm

    assert self._locked
    self._locked = False
    resume_alarm()

  @contextmanager
  def lock(self):
    """Create a context manager for a lock."""
    self.acquire()
    try:
      yield
    finally:
      self.release()

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
  ZERO       = 0
  CONFIG     = 1
  CHECKSUM   = 2
  FETCH      = 3
  BUILD      = 4
  INSTALL    = 5
  PKGINSTALL = 6

  _config_lock = Lock()
  _checksum_lock = FileLock()
  _fetch_lock = FileLock()
  _bad_checksum = set()
  _fetched = set()
  _fetch_failed = set()

  def __init__(self, origin, attr):
    """Itialise the port with the required information."""
    from ..signal import Signal
    from .mk import status
    from .dependhandler import Dependant

    self.attr = attr
    self.log_file = None
    self.failed = False
    self.load = attr["jobs_number"]
    self.origin = origin
    self.priority = 0
    self.working = False

    self.stage = Port.ZERO
    self.stage_completed = Signal()
    self.install_status = status(self)

    self.dependancy = None
    self.dependant = Dependant(self)

  def __repr__(self):
    return "<Port(origin=%s)>" % (self.origin)

  def clean(self):
    """Clean the ports working directory any log file."""
    pass

  def build_stage(self, stage):
    """Build the requested stage."""
    from time import time
    from ..job import StalledJob

    pre_map = (self._pre_config, self._pre_checksum, self._pre_fetch,
                self._pre_build, self._pre_install)

    if self.working or self.stage != stage - 1 or self.failed:
      return False
    if self.stage >= Port.CONFIG and self.dependancy.check(stage):
      return False

    self.working = time()
    try:
      status = pre_map[stage - 1]()
      if status is not None:
        self._finalise(stage - 1, status)
    except StalledJob:
      self.working = False
      raise
    return True

  def _pre_config(self):
    """Configure the ports options."""
    if len(self.attr["options"]) and not self._check_config():
      if not self._config_lock.acquire():
        from ..job import StalledJob
        raise StalledJob()
      self._make_target("config", pipe=False)
    else:
      self._load_dependancy()

  def _post_config(self, _make, status):
    """Refetch attr data if ports were configured successfully."""
    self._config_lock.release()
    if status:
      from .mk import attr

      attr(self.origin, self._load_attr, True)
      return None
    return status

  def _load_attr(self, _origin, attr):
    """Load the attributes for this port."""
    if attr is None:
      self._finalise(self.stage, False)
      return
    else:
      self.attr = attr
      self._load_dependancy()

  def _load_dependancy(self):
    """Create a dependancy object for this port."""
    from os.path import join
    from .dependhandler import Dependancy

    LOG_DIR = "/tmp/pypkg"
    self.log_file = join(LOG_DIR, self.attr["uniquename"])
    self.priority = self._get_priority()
    self.dependant.priority += self.priority
    depends = ('depend_build', 'depend_extract', 'depend_fetch', 'depend_lib',
               'depend_run', 'depend_patch')
    self.dependancy = Dependancy(self, [self.attr[i] for i in depends])

  def dependancy_loaded(self, status):
    """Informs port that dependancy loading has completed."""
    self._finalise(self.stage, status)

  def _pre_checksum(self):
    """Check if distfiles are available."""
    from os.path import join, isfile
    from ..env import flags

    if flags["no_op"]:
      return True

    distfiles = self.attr["distfiles"]
    if self._fetched.issuperset(distfiles):
      self.stage = Port.FETCH
      return True
    if not self._bad_checksum.isdisjoint(distfiles):
      return True
    distdir = self.attr["distdir"]
    for i in distfiles:
      if not isfile(join(distdir, i)):
        self._bad_checksum.add(i)
        return True
    if not self._checksum_lock.acquire(distfiles):
      from ..job import StalledJob
      raise StalledJob()
    else:
      self._make_target("checksum", BATCH=True, FETCH_REGET=0)

  def _post_checksum(self, _make, status):
    """Advance to build stage if checksum passed."""
    distfiles = self.attr["distfiles"]
    self._checksum_lock.release(distfiles)
    if status:
      self.stage = Port.FETCH
    else:
      self._bad_checksum.update(distfiles)
    return True

  def _pre_fetch(self):
    """Fetch the ports files."""
    distfiles = self.attr["distfiles"]
    if self._fetched.issuperset(distfiles):
      return True
    if self._fetch_failed.issuperset(distfiles):
      return False
    if not self._fetch_lock.acquire(distfiles):
      from ..job import StalledJob
      raise StalledJob()
    else:
      self._make_target("checksum", BATCH=True, NO_DEPENDS=True)

  def _post_fetch(self, _make, status):
    """Register fetched files if fetch succeeded."""
    distfiles = self.attr["distfiles"]
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
    self._make_target(["clean","all"], BATCH=True, NOCLEANDEPENDS=True, NO_DEPENDS=True)

  def _post_build(self, _make, status):
    """Indicate build status."""
    return status

  def _pre_install(self):
    """Install the port."""
    if self.install_status == Port.ABSENT:
      target = "install"
    else:
      target = ("deinstall", "reinstall")
    # TODO: package
    self._make_target(target, BATCH=True, NO_DEPENDS=True)

  def _post_install(self, _make, status):
    """Update the install status."""
    if status:
      from ..env import flags
      from .mk import status

      if flags["no_op"]:
        self.install_status = Port.CURRENT
      else:
        self.install_status = status(self, True)
    else:
      # TODO???
      self.install_status = Port.ABSENT
    return status

  def _make_target(self, targets, **kwargs):
    """Build the requested targets."""
    from ..make import make_target

    make_target(self._make, self, targets, **kwargs)

  def _make(self, make):
    """Call the _post_[stage] function and finalise the stage."""
    from ..make import SUCCESS

    post_map = (self._post_config, self._post_checksum, self._post_fetch,
                self._post_build, self._post_install)
    stage = self.stage
    status = post_map[stage](make, make.wait() is SUCCESS)
    if status is not None:
      self._finalise(stage, status)

  def _finalise(self, stage, status):
    """Finalise the stage."""
    if not status:
      self.failed = True
    self.working = False
    self.stage = max(stage + 1, self.stage)
    self.stage_completed(self)
    if self.failed or self.stage >= Port.INSTALL:
      self.dependant.status_changed()

  def _check_config(self):
    """Check the options file to see if it is up-to-date."""
    from os.path import isfile

    # TODO: make this understand about options set, changes and versioning...
    optionfile = self.attr["optionsfile"]
    pkgname = self.attr["pkgname"]
    options = set()
    if isfile(optionfile):
      for i in open(optionfile, 'r'):
        if i.startswith('_OPTIONS_READ='):
          # The option set to the last pkgname this config file was set for
          config_pkgname = i[14:-1]
        elif i.startswith('WITH'):
          options.add(i.split('_', 1)[1].split('=', 1)[0])
    if options != set(self.attr["options"]):
      return False
    # if diff_version:
    #   return config_pkgname == pkgname
    return True

  def _get_priority(self):
    """Get the priority of this port, based on the distfiles size."""
    from os.path import isfile

    distfiles = self.attr["distfiles"]
    if not len(distfiles) or not isfile(self.attr["distinfo"]):
      return 0
    priority = 0
    for i in open(self.attr["distinfo"], 'r'):
      if i.startswith("SIZE"):
        i = i.split()
        name, size = i[1], i[-1]
        name = name[1:-1]
        name = name.split('/')[-1]
        if name in distfiles:
          priority += int(size)
    return priority
