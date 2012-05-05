"""Modelling of FreeBSD ports."""

from __future__ import absolute_import

from contextlib import contextmanager
import os
import time

from libpb import env, log, make, mk, pkg

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
    """
    A FreeBSD port class.

    Signals:
     - stage_completed(Port):     Indicates the port completed a stage

    The port has multiple stages that it may be in.  The progression is as
    follows:
        For the "build" method:
            ZERO -> CONFIG -> DEPEND (-> CHECKSUM) (->FETCH) -> BUILD -> INSTALL
                (-> PACKAGE)
        For the "package" method:
            ZERO -> CONFIG -> DEPEND -> PKGINSTALL
        For the "repo" method:
            ZERO -> CONFIG -> DEPEND -> REPOCONFIG (-> REPOFETCH) -> REPOINSTALL

    The CHECKSUM and FETCH stage may be skipped if either there are no distfiles
    for the port or the distfiles have already been checked.  Furthermore, the
    CHECKSUM stage may be skipped if the distfiles have already failed checksum.

    The REPOFETCH stage may be skipped if the package has already been retrieved
    from the repository.
    """

    # Installed status flags
    ABSENT  = 0
    OLDER   = 1
    CURRENT = 2
    NEWER   = 3

    # Build stage status flags
    ZERO        = 0
    CONFIG      = 1
    DEPEND      = 2
    CHECKSUM    = 3
    FETCH       = 4
    BUILD       = 5
    INSTALL     = 6
    PACKAGE     = 7
    PKGINSTALL  = 8
    REPOCONFIG  = 9
    REPOFETCH   = 10
    REPOINSTALL = 11

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
        self.flags = set()
        self.failed = False
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

    def resolved(self):
        """Indicate if the port meets it's dependencies."""
        # TODO: use Dependent.RESOLV (current import issues)
        RESOLV = 1
        assert (self.dependent.status != RESOLV or
          (self.install_status > env.flags["stage"] or "upgrade" in self.flags))
        status = env.flags["stage"]
        if "upgrade" in self.flags and status < pkg.OLDER:
            status = pkg.OLDER
        return (self.install_status > status and
                self.dependent.status == RESOLV)

    def clean(self, force=False):
        """Remove port's working director and log files."""
        assert not self.working or self.stage < Port.BUILD or \
               env.flags["mode"] == "clean"

        if self.stage >= Port.BUILD:
            self.working = time.time()

        if Port.BUILD <= self.stage <= Port.PACKAGE or force:
            mak = make.make_target(self, "clean", NOCLEANDEPENDS=True)
            log.debug("Port.clean()", "Port '%s': full clean" % self.origin)
            return mak.connect(self._post_clean)
        else:
            self._post_clean()
            log.debug("Port.clean()", "Port '%s': quick clean" % self.origin)
            return True

    def _post_clean(self, pmake=None):
        """Remove log file."""
        if self.stage >= Port.BUILD:
            self.working = False
        if pmake and pmake.wait():
            self.failed = True
        if not self.failed and os.path.isfile(self.log_file) and \
                (env.flags["mode"] == "clean" or self.stage >= Port.BUILD or
                 (self.dependency and self.dependency.failed)):
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
        else:
            # Start from the beginning
            self.stage = Port.ZERO

    def build_stage(self, stage):
        """Build the requested stage."""
        from ..job import StalledJob

        assert not self.working
        assert not self.failed
        assert self.stage == stage - 1
        assert self.stage < Port.DEPEND or not self.dependency.check(stage)

        pre_map = (self._pre_config, self._pre_depend, self._pre_checksum,
                   self._pre_fetch, self._pre_build, self._pre_install,
                   self._pre_package, None)

        if self.working or self.stage != stage - 1 or self.failed or (
            self.stage >= Port.DEPEND and self.dependency.check(stage)):
            # Don't do stage if not able to
            if self.working:
                msg = "already busy"
            elif self.stage != stage - 1:
                msg = "haven't completed previous stage"
            elif self.failed:
                msg = "port failed previous stage"
            elif self.stage >= Port.DEPEND and self.dependency.check(stage):
                msg = "dependencies not resolved"
            log.error("Port.build_stage()", ("Port '%s': cannot build stage "
                      "%i: %s" % (self.origin, stage, msg),))
            return False

        log.debug("Port.build_stage()",
                  "Port '%s': building stage %i" % (self.origin, stage))
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
            if self._fetched.issuperset(self.attr["distfiles"]):
                # NOTE: if no distfiles above is always true
                self.stage = Port.FETCH
            return True
        if not self._config_lock.acquire():
            from ..job import StalledJob
            raise StalledJob()
        return self._make_target("config", pipe=False)

    def _post_config(self, _make, status):
        """Refetch attr data if ports were configured successfully."""
        self._config_lock.release()
        if status:
            mk.Attr(self.origin).connect(self._load_attr).get()
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

    def _post_depend(self, status):
        """Advance to the build stage if nothing to fetch."""
        if status:
            if self._fetched.issuperset(self.attr["distfiles"]):
                # NOTE: if no distfiles above is always true
                # If files have already been fetched
                self.stage = Port.FETCH
            elif not self._bad_checksum.isdisjoint(self.attr["distfiles"]):
                # If some files have already failed
                self.stage = Port.CHECKSUM
        self._finalise(Port.CONFIG, status)

    def _pre_checksum(self):
        """Check if distfiles are available."""
        from ..env import flags

        if flags["no_op"]:
            return True

        distfiles = self.attr["distfiles"]
        if self._fetched.issuperset(distfiles):
            # NOTE: if no distfiles above is always true
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
            return self._make_target("checksum", BATCH=True, NO_DEPENDS=True,
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
            # NOTE: if no distfiles above is always true
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
            files = ", ".join("'%s'" % i for i in distfiles)
            log.debug("Port._post_fetch()",
                      "Port '%s': failed to fetch distfiles: %s" %
                          (self.origin, files))
            self._bad_checksum.update(distfiles)
            self._fetch_failed.update(distfiles)
        return status

    def _pre_build(self):
        """Build the port."""
        return self._make_target(("all",), BATCH=True, NO_DEPENDS=True)

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
        self.install_status = pkg.db.status(self)
        return status

    def _pre_package(self):
        """Package the port,"""
        return self._make_target("package", BATCH=True, NO_DEPENDS=True)

    @staticmethod
    def _post_package(_make, status):
        """Indicate package status."""
        return status

    def repoinstall(self):
        """Prepare to install the port from a repository."""
        assert not self.working
        assert not self.failed
        assert self.DEPEND <= self.stage < self.BUILD
        assert not self.dependency.check(Port.REPOINSTALL)

        log.debug("Port.repoinstall()", "Port '%s': building stage %i" %
                      (self.origin, Port.REPOINSTALL))

        if (self.working or self.attr["no_package"]):
            return False

        self.stage = Port.REPOINSTALL - 1
        self.working = time.time()
        if self.install_status > Port.ABSENT:
            return make.make_target(self, "deinstall").connect(self._repoinstall)
        else:
            return self._repoinstall()

    def pkginstall(self):
        """Prepare to install the port from it's package."""
        assert not self.working
        assert not self.failed
        assert self.DEPEND <= self.stage < self.BUILD
        assert not self.dependency.check(Port.PKGINSTALL)

        log.debug("Port.pkginstall()", "Port '%s': building stage %i" %
                      (self.origin, Port.PKGINSTALL))

        if (self.working or self.attr["no_package"] or
            not os.path.isfile(env.flags["chroot"] + self.attr["pkgfile"])):
            return False

        self.stage = Port.PKGINSTALL - 1
        self.working = time.time()
        if self.install_status > Port.ABSENT:
            return make.make_target(self, "deinstall").connect(self._pkginstall)
        else:
            return self._pkginstall()

    def _repoinstall(self, pmake=None):
        """Install the port from a repository package."""
        return self._pkginstall(pmake, True)

    def _pkginstall(self, pmake=None, repo=False):
        """Install the port from it's package."""
        if pmake is not None:
            status = pmake.wait() == make.SUCCESS
            if not status:
                self.stage = Port.REPOINSTALL if repo else Port.PKGINSTALL
                self.working = False
                self.stage_completed.emit(self)
                self.failed = True
                log.error("Port._pkginstall()", "Port '%s': failed stage %d" %
                              (self.origin, self.stage))
            else:
                pkg.db.remove(self)
            self.dependent.status_changed()
            if not status:
                return

        pkg_add = pkg.add(self, repo)
        if pkg_add:
            if repo:
                pkg_add.connect(self._post_repoinstall)
            else:
                pkg_add.connect(self._post_pkginstall)
        return pkg_add

    def _post_repoinstall(self, pkg_add):
        """Report if the port successfully installed from it's package."""
        self._post_pkginstall(pkg_add, True)

    def _post_pkginstall(self, pkg_add, repo=False):
        """Report if the port successfully installed from it's package."""
        self.working = False
        self.stage = Port.REPOINSTALL if repo else Port.PKGINSTALL

        if pkg_add.wait() == make.SUCCESS:
            pkg.db.add(self)
            log.error("Port._post_pkginstall()",
                     "Port '%s': finished stage %d" % (self.origin, self.stage))
        else:
            log.error("Port._port_pkginstall()", "Port '%s': failed stage %d" %
                      (self.origin, self.stage))
            self.failed = True

        self.install_status = pkg.db.status(self)
        self.stage_completed.emit(self)

        self.dependent.status_changed()

    def _make_target(self, targets, **kwargs):
        """Build the requested targets."""
        from ..make import make_target

        return make_target(self, targets, **kwargs).connect(self._make)

    def _make(self, pmake):
        """Call the _post_[stage] function and finalise the stage."""
        post_map = (self._post_config, None, self._post_checksum,
                    self._post_fetch, self._post_build, self._post_install,
                    self._post_package, None)
        stage = self.stage
        status = post_map[stage](pmake, pmake.wait() == make.SUCCESS)
        if status is not None:
            self._finalise(stage, status)

    def _finalise(self, stage, status):
        """Finalise the stage."""
        if not status:
            log.error("Port._finalise()", "Port '%s': failed stage %d" %
                          (self.origin, stage + 1))
            self.failed = True
        else:
            log.debug("Port._finalise()", "Port '%s': finished stage %d" %
                          (self.origin, stage + 1))
        self.working = False
        self.stage = max(stage + 1, self.stage)
        self.stage_completed.emit(self)
        if (self.failed or
                self.stage >= (Port.FETCH if env.flags["fetch_only"] else
                    Port.INSTALL)):
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
