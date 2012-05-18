"""
The stacks.common module.  This module contains the common Stages required for
all other Stacks.
"""

import contextlib
import os

from libpb import env, event, job, mk, pkg
from libpb.stacks import base, mutators

__all__ = ["Config", "Depend"]


class Lock(object):
    """A simple Uniprocessor lock."""

    def __init__(self):
        """Initialise lock."""
        self._locked = False

    def acquire(self):
        """Acquire lock."""
        if self._locked:
            return False
        self._locked = True
        event.suspend()
        return True

    def release(self):
        """Release lock."""
        assert self._locked
        self._locked = False
        event.resume()

    @contextlib.contextmanager
    def lock(self):
        """Create a context manager for a lock."""
        self.acquire()
        try:
            yield
        finally:
            self.release()


class Config(mutators.MakeStage):
    """Configure a port."""

    name = "config"
    stack = "common"

    _config_lock = Lock()

    def complete(self):
        """Check the options file to see if it is up-to-date."""
        if not self.port.attr["options"] or env.flags["config"] == "none":
            return True
        elif env.flags["config"] == "all":
            return False

        optionfile = env.flags["chroot"] + self.port.attr["optionsfile"]
        pkgname = self.port.attr["pkgname"]
        options = set()
        if os.path.isfile(optionfile):
            with open(optionfile, 'r') as optionfile:
                for i in optionfile:
                    if i.startswith('_OPTIONS_READ='):
                        # The option set to the last pkgname this config file
                        # was set for
                        config_pkgname = i[14:-1]
                    elif i.startswith('WITH'):
                        options.add(i.split('_', 1)[1].split('=', 1)[0])
        if (env.flags["config"] == "changed" and
                options != set(self.port.attr["options"])):
            return False
        if (env.flags["config"] == "newer" and
            pkg.version(pkgname, config_pkgname) == pkg.NEWER) :
            return False
        return True

    def _pre_make(self):
        """Issue a make.target() to configure the port."""
        if not Config._config_lock.acquire():
            raise job.StalledJob()
        self._make_target("config", pipe=False)

    def _post_make(self, status):
        """Refetch attr data if ports were configured successfully."""
        self._config_lock.release()
        if status:
            mk.Attr(self.port.origin).connect(self._load_attr).get()
            return None
        return status

    def _load_attr(self, _origin, attr):
        """Load the attributes for this port."""
        if attr:
            self.port.attr = attr
            log_file = self.port.log_file
            self.port.log_file = os.path.join(env.flags["log_dir"],
                                              self.port.attr["pkgname"])
            if log_file != self.port.log_file and os.path.isfile(log_file):
                os.rename(log_file, self.port.log_file)
        self._finalise(attr is not None)


class Depend(base.Stage):
    """Load a port's dependencies."""

    name = "depend"
    prev = Config
    stack = "common"
