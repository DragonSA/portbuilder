"""Modelling of FreeBSD ports."""

from __future__ import absolute_import

from contextlib import contextmanager
import os
import subprocess
import time

from libpb import pkg

from ..signal import SignalProperty

__all__ = ["Port"]

# TODO:
# Non-privileged mode
# remove NO_DEPENDS once thoroughly tested???
# handle IS_INTERACTIVE


class Lock(object):
    """A simple Uniprocessor lock."""

    def __init__(self):
        """Initialise lock."""
        self._locked = False

    def acquire(self):
        """Acquire lock."""
        from ..event import suspend

        if self._locked:
            return False
        self._locked = True
        suspend()
        return True

    def release(self):
        """Release lock."""
        from ..event import resume

        assert self._locked
        self._locked = False
        resume()

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
    """A FreeBSD port class.

    Signals:
     - stage_completed(Port):     Indicates the port completed a stage
    """

    # Installed status flags
    ABSENT  = 0
    OLDER   = 1
    CURRENT = 2
    NEWER   = 3

    # Build stage status flags
    ZERO       = 0
    CONFIG     = 1
    DEPEND     = 2
    CHECKSUM   = 3
    FETCH      = 4
    BUILD      = 5
    INSTALL    = 6
    PACKAGE    = 7
    PKGINSTALL = 8

    _config_lock = Lock()
    _checksum_lock = FileLock()
    _fetch_lock = FileLock()
    _bad_checksum = set()
    _fetched = set()
    _fetch_failed = set()

    stage_completed = SignalProperty("stage_completed")

    def __init__(self, origin, attr):
        """Initialise the port with the required information."""
        from .dependhandler import Dependent
        from ..env import flags

        self.attr = attr
        self.log_file = os.path.join(flags["log_dir"], self.attr["pkgname"])
        self.failed = False
        self.force = False
        self.load = attr["jobs_number"]
        self.origin = origin
        self.priority = 0
        self.working = False

        self.stage = Port.ZERO
        self.install_status = pkg.db.status(self)

        self.dependency = None
        self.dependent = Dependent(self)

        if not len(self.attr["options"]) or self._check_config():
            self.stage = Port.CONFIG

    def __lt__(self, other):
        return self.dependent.priority > other.dependent.priority

    def __repr__(self):
        return "<Port(%s)>" % (self.origin)

    def clean(self):
        """Clean the ports working directory and log file."""
        from ..env import flags

        assert not self.working or flags["mode"] == "clean"
        if Port.BUILD <= self.stage < Port.PKGINSTALL:
            from ..job import CleanJob
            from ..queue import clean_queue

            clean_queue.add(CleanJob(self).connect(self._cleaned))
        else:
            self._cleaned()

    def _cleaned(self, job=None):
        """Mark the port as clean."""
        self.working = False
        if job and not job.status:
            self.failed = True
        if not self.failed and os.path.isfile(self.log_file):
            os.unlink(self.log_file)

    def reset(self):
        """Reset the ports state, and stage."""
        assert not self.working
        self.failed = False
        if self.dependency is not None:
            if self._fetched.issuperset(self.attr["distfiles"]):
                # If files are already fetched
                self.stage = Port.FETCH
            else:
                # If dependency already loaded
                self.stage = Port.DEPEND
        elif not len(self.attr["options"]) or self._check_config():
            # If no need to configure port
            self.stage = Port.CONFIG

    def build_stage(self, stage):
        """Build the requested stage."""
        from ..job import StalledJob

        pre_map = (self._pre_config, self._pre_depend, self._pre_checksum,
                   self._pre_fetch, self._pre_build, self._pre_install,
                   self._pre_package, None)

        if self.working or self.stage != stage - 1 or self.failed:
            # Don't do stage if not able to
            return False
        if self.stage >= Port.DEPEND and self.dependency.check(stage):
            # Don't do stage if not configured
            return False

        self.working = time.time()
        try:
            status = pre_map[stage - 1]()
            if isinstance(status, bool):
                self._finalise(stage - 1, status)
                return True
        except StalledJob:
            self.working = False
            raise
        return status

    def _pre_config(self):
        """Configure the ports options."""
        if self._check_config():
            return True
        if not self._config_lock.acquire():
            from ..job import StalledJob
            raise StalledJob()
        return self._make_target("config", pipe=False)

    def _post_config(self, _make, status):
        """Refetch attr data if ports were configured successfully."""
        self._config_lock.release()
        if status:
            from .mk import Attr

            Attr(self.origin).connect(self._load_attr).get()
            return None
        return status

    def _load_attr(self, _origin, attr):
        """Load the attributes for this port."""
        from ..env import flags

        self.attr = attr
        log_file = self.log_file
        self.log_file = os.path.join(flags["log_dir"], self.attr["pkgname"])
        if log_file != self.log_file and os.path.isfile(log_file):
            os.rename(log_file, self.log_file)
        self._finalise(self.stage, attr is not None)

    def _pre_depend(self):
        """Create a dependency object for this port."""
        from .dependhandler import Dependency

        self.priority = self._get_priority()
        self.dependent.priority += self.priority
        depends = ("depend_build", "depend_extract", "depend_fetch",
                   "depend_lib", "depend_run", "depend_patch", "depend_package")
        self.dependency = Dependency(self, [self.attr[i] for i in depends])

    def _pre_checksum(self):
        """Check if distfiles are available."""
        from ..env import flags

        if flags["no_op"]:
            return True

        distfiles = self.attr["distfiles"]
        if self._fetched.issuperset(distfiles):
            # If files are already fetched
            self.stage = Port.FETCH
            return True
        if not self._bad_checksum.isdisjoint(distfiles):
            # If some files have already failed
            return True
        distdir = self.attr["distdir"]
        for i in distfiles:
            if not os.path.isfile(os.path.join(flags["chroot"] + distdir, i)):
                # If file does not exist then it failed
                self._bad_checksum.add(i)
                return True
        if not self._checksum_lock.acquire(distfiles):
            from ..job import StalledJob
            raise StalledJob()
        else:
            return self._make_target("checksum", BATCH=True,
                                     DISABLE_CONFLICTS=True, FETCH_REGET=0)

    def _post_checksum(self, _make, status):
        """Advance to build stage if checksum passed."""
        distfiles = self.attr["distfiles"]
        self._checksum_lock.release(distfiles)
        if status:
            self._fetched.update(distfiles)
            self.stage = Port.FETCH
        else:
            self._bad_checksum.update(distfiles)
        return True

    def _pre_fetch(self):
        """Fetch the ports files."""
        distfiles = self.attr["distfiles"]
        if self._fetched.issuperset(distfiles):
            # If files are already fetched
            return True
        if self._fetch_failed.issuperset(distfiles):
            # If files have failed to fetch
            return False
        if not self._fetch_lock.acquire(distfiles):
            from ..job import StalledJob
            raise StalledJob()
        else:
            return self._make_target("checksum", BATCH=True,
                                     DISABLE_CONFLICTS=True, NO_DEPENDS=True)

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
        return self._make_target(["clean","all"], BATCH=True,
                                 NOCLEANDEPENDS=True, NO_DEPENDS=True)

    @staticmethod
    def _post_build(_make, status):
        """Indicate build status."""
        return status

    def _pre_install(self):
        """Install the port."""
        if self.install_status == Port.ABSENT:
            target = ("install",)
        else:
            target = ("deinstall", "reinstall")
        return self._make_target(target, BATCH=True, NO_DEPENDS=True)

    def _post_install(self, _make, status):
        """Update the install status."""
        if self.install_status != Port.ABSENT:
            pkg.db.remove(self)
        if status:
            pkg.db.add(self)
        else:
            # TODO???
            pass
        self.install_status = pkg.db.status(self)
        return status

    def _pre_package(self):
        """Package the port,"""
        return self._make_target("package", BATCH=True)

    @staticmethod
    def _post_package(_make, status):
        """Indicate package status."""
        return status

    def pkginstall(self):
        """Prepare to install the port from it's package."""
        # TODO: proper asserts (valid stage).
        from ..env import flags
        from ..make import make_target

        if (self.working or self.attr["no_package"] or
            not os.path.isfile(flags["chroot"] + self.attr["pkgfile"])):
            return False

        self.stage = Port.PKGINSTALL - 1
        self.working = time.time()
        if self.install_status > Port.ABSENT:
            return make_target(self, "deinstall").connect(self._pkginstall)
        else:
            return self._pkginstall()

    def _pkginstall(self, make=None):
        """Install the port from it's package."""
        from ..env import flags
        from ..make import SUCCESS

        if make is not None:
            status = make.wait() == SUCCESS
            if not status:
                self.stage = Port.PKGINSTALL
                self.working = False
                self.stage_completed.emit(self)
            else:
                pkg.db.remove(self)
            self.dependent.status_changed()
            if not status:
                return

        return pkg.add(self).connect(self._post_pkginstall)

    def _post_pkginstall(self, pkg_add):
        """Report if the port successfully installed from it's package."""
        from ..env import flags
        from ..make import SUCCESS

        self.working = False
        success = pkg_add.wait() == SUCCESS
        if success:
            pkg.db.add(self)

        self.install_status = pkg.db.status(self)
        self.failed = not success
        self.stage = Port.PKGINSTALL
        self.stage_completed.emit(self)

        self.dependent.status_changed()

    def _make_target(self, targets, **kwargs):
        """Build the requested targets."""
        from ..make import make_target

        return make_target(self, targets, **kwargs).connect(self._make)

    def _make(self, make):
        """Call the _post_[stage] function and finalise the stage."""
        from ..make import SUCCESS

        post_map = (self._post_config, None, self._post_checksum,
                    self._post_fetch, self._post_build, self._post_install,
                    self._post_package, None)
        stage = self.stage
        status = post_map[stage](make, make.wait() == SUCCESS)
        if status is not None:
            self._finalise(stage, status)

    def _finalise(self, stage, status):
        """Finalise the stage."""
        from ..env import flags

        if not status:
            self.failed = True
        self.working = False
        self.stage = max(stage + 1, self.stage)
        self.stage_completed.emit(self)
        if (self.failed or
            self.stage >= (Port.FETCH if flags["fetch_only"] else Port.INSTALL)):
            self.dependent.status_changed()

    def _check_config(self):
        """Check the options file to see if it is up-to-date."""
        from ..env import flags

        if flags["config"] == "none":
            return True
        elif flags["config"] == "all":
            return False

        optionfile = flags["chroot"] + self.attr["optionsfile"]
        pkgname = self.attr["pkgname"]
        options = set()
        if os.path.isfile(optionfile):
            for i in open(optionfile, 'r'):
                if i.startswith('_OPTIONS_READ='):
                    # The option set to the last pkgname this config file was
                    # set for
                    config_pkgname = i[14:-1]
                elif i.startswith('WITH'):
                    options.add(i.split('_', 1)[1].split('=', 1)[0])
        if flags["config"] == "changed" and options != set(self.attr["options"]):
            return False
        if (flags["config"] == "newer" and
            pkg.version(pkgname, config_pkgname) == Port.NEWER) :
            return False
        return True

    def _get_priority(self):
        """Get the priority of this port, based on the distfiles size."""
        from ..env import flags

        distfiles = self.attr["distfiles"]
        distinfo = flags["chroot"] + self.attr["distinfo"]
        if not len(distfiles) or not os.path.isfile(distinfo):
            return 0
        priority = 0
        for i in open(distinfo, 'r'):
            if i.startswith("SIZE"):
                i = i.split()
                name, size = i[1], i[-1]
                name = name[1:-1]
                name = name.split('/')[-1]
                if name in distfiles:
                    priority += int(size)
        return priority
