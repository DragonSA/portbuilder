"""
The stacks.build module.  This module contains the Stages that make up the
"build" Stack.
"""

import contextlib
import os

from libpb import env, job, log, pkg, queue
from libpb.stacks import base, common, mutators

__all__ = ["Checksum", "Fetch", "Build", "Install", "Package"]


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

    @contextlib.contextmanager
    def lock(self, files):
        """Create a context manager for a lock of the given files."""
        self.acquire(files)
        try:
            yield
        finally:
            self.release(files)


class Distfiles(base.Stage):
    """A stage that accesses the distfiles for a port."""

    _bad_checksum = set()
    _fetched = set()
    _fetch_failed = set()


class Checksum(Distfiles, mutators.MakeStage):
    """Check if the port's files are available."""

    name = "Checksum"
    prev = common.Depend
    stack = "build"

    _checksum_lock = FileLock()

    def complete(self):
        """Check if any of the distfiles have been checked."""
        if env.flags["no_op"]:
            return True
        distfiles = self.port.attr["distfiles"]
        if Checksum._fetched.issuperset(distfiles):
            # NOTE: if no distfiles above is always true
            return True
        if not Checksum._bad_checksum.isdisjoint(distfiles):
            # If some files have already failed
            return True
        distdir = self.port.attr["distdir"]
        for i in distfiles:
            if not os.path.isfile(os.path.join(env.flags["chroot"] + distdir, i)):
                # If file does not exist then it failed
                Checksum._bad_checksum.add(i)
                return True
        return False

    def _pre_make(self):
        """Issue a make.target() to check the distfiles."""
        if not Checksum._checksum_lock.acquire(self.port.attr["distfiles"]):
            raise job.StalledJob()
        else:
            self._make_target("checksum", BATCH=True, NO_DEPENDS=True,
                                          DISABLE_CONFLICTS=True, FETCH_REGET=0)

    def _post_make(self, status):
        """Process the results of make.target()."""
        distfiles = self.port.attr["distfiles"]
        self._checksum_lock.release(distfiles)
        if status:
            self._fetched.update(distfiles)
        else:
            self._bad_checksum.update(distfiles)
        return True


class Fetch(Distfiles, mutators.MakeStage):
    """Fetch a port's files."""

    name = "Fetch"
    prev = Checksum
    stack = "build"

    _fetch_lock = FileLock()

    @staticmethod
    def check(port):
        """Check if any distfiles have failed to fetch."""
        # If files have failed to fetch
        return not (port.attr["distfiles"] and
                    Fetch._fetch_failed.issuperset(port.attr["distfiles"]))

    def complete(self):
        """Check if all distfiles have been fetched."""
        # NOTE: if no distfiles above is always true
        # If files are already fetched
        return self._fetched.issuperset(self.port.attr["distfiles"])

    def _pre_make(self):
        """Issue a make.target() command to fetch outstanding distfiles,"""
        if not Fetch._fetch_lock.acquire(self.port.attr["distfiles"]):
            raise job.StalledJob()
        else:
            self._make_target("checksum", BATCH=True, DISABLE_CONFLICTS=True,
                                          NO_DEPENDS=True)

    def _post_make(self, status):
        """Process the results of make.target()."""
        distfiles = set(self.port.attr["distfiles"])
        self._fetch_lock.release(distfiles)
        if status:
            self._bad_checksum.difference_update(distfiles)
            self._fetched.update(distfiles)
        else:
            files = ", ".join("'%s'" % i for i in distfiles)
            log.debug("Fetch._post_make()",
                      "Fetch '%s': failed to fetch distfiles: %s" %
                          (self.port.origin, files))
            self._bad_checksum.update(distfiles)
            self._fetch_failed.update(distfiles)
        # TODO:
        # - extend queue to handle non-active "done" jobs
        # - make queue finish via signal, not direct call to queue.done
        # ? track which jobs are handling which distfiles (cleanup with done())
        # Go through all the pending fetch jobs and see if any have been
        # resolved due to this job:
        for q in (queue.fetch.stalled, queue.fetch.queue):
            for i in range(len(q) - 1, -1, -1):
                j = q[i]
                if (isinstance(j, Fetch) and
                        not distfiles.isdisjoint(j.port.attr["distfiles"]) and
                        (not j.check(j.port) or j.complete())):
                    del q[i]
                    j.run()
        return status


class Build(mutators.MakeStage, mutators.PostFetch):
    """Build a port."""

    name = "Build"
    prev = Fetch
    stack = "build"

    def __init__(self, port):
        super(Build, self).__init__(port, port.attr["jobs_number"])

    def _pre_make(self):
        """Issue a make.target() to build the port."""
        self._make_target(("all",), BATCH=True, NO_DEPENDS=True)


class Install(mutators.Deinstall, mutators.MakeStage, mutators.PostFetch,
              mutators.Resolves):
    """Install a port from source."""

    name = "Install"
    prev = Build
    stack = "build"

    def _pre_make(self):
        """Issue a make.target() to install the port."""
        if self.port.install_status == pkg.ABSENT:
            target = ("install",)
        else:
            target = ("deinstall", "reinstall")
        # pylint: disable-msg=E1101
        # NOTE: pylint doesn't detect self._make_target() inherited from
        # mutators.MakeStage()
        if "explicit" in self.port.flags:
            self._make_target(target, BATCH=True, NO_DEPENDS=True)
        else:
            self._make_target(target, BATCH=True, NO_DEPENDS=True,
                                      INSTALLS_DEPENDS=True)


class Package(mutators.MakeStage, mutators.Packagable, mutators.PostFetch):
    """Package a port."""

    name = "Package"
    prev = Install
    stack = "build"

    def _pre_make(self):
        """Issue a make.target() to package the port,"""
        self._make_target("package", BATCH=True, NO_DEPENDS=True)
