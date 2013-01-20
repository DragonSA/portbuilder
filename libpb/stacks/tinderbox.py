"""
The stacks.build module.  This module contains the Stages that make up the
"build" Stack.
"""

import os
import subprocess

from libpb import env, make
from libpb.stacks import base, build, common, mutators

__all__ = ["Checksum", "Fetch", "Build", "Install", "Package"]


class Tinderbox(mutators.MakeStage, mutators.Packagable, mutators.PostFetch,
                mutators.Resolves):
    """Package a port in a "tinderbox"."""

    name = "Tinderbox"
    prev = build.Fetch
    stack = "tinderbox"

    chroot_make = "false"
    chroot_clean = "false"
    chroot_dir = None

    chroot_count = 0

    def __init__(self, port):
        super(Tinderbox, self).__init__(port)
        Tinderbox.chroot_count += 1
        self.chroot = os.path.join(chroot_dir, "%06i" % Tinderbox.chroot_count)

    def _pre_make(self):
        """Create the chroot environment"""
        hook = self._hook(Tinderbox.chroot_make)
        self.pid = hook.connect(self._do_make).pid

    def _do_make(self, status):
        """Issue a make.target() to package the port."""
        if pmake.wait() == make.SUCCESS:
            self._make_target("package", chroot=self.chroot, BATCH=True,
                              USE_PACKAGE_DEPENDS=True)
        else:
            self.pid = None
            self._finalise(False)

    def _post_make(self, status):
        """Cleanup "tinderbox"."""
        self._hook(Tinderbox.chroot_clean)
        return status

    def _hook(self, script):
        """Run hook script"""
        args = (script, self.chroot)
        stdin = subprocess.PIPE
        stdout = open(port.log_file, 'a')
        stderr = stdout
        stdout.write("# %s\n" % " ".join(args))
        if env.flags["no_op"]:
            hook = PopenNone(args, self.port)
        else:
            hook = Popen(args, self.port, stdin=stdin, stdout=stdout, stderr=stderr)
            hook.stdin.close()
        return hook
