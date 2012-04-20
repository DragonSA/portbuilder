"""Make targets."""

from __future__ import absolute_import

import errno
import os
import subprocess

from .signal import Signal

__all__ = ["SUCCESS", "make_target"]

SUCCESS = 0

# HACK !!!
def _eintr_retry_call(func, *args):
    """HACK: do not wait for subprocesses to report ready.

    Popen uses read to get subprocess status, prevent it from being called"""
    if func.__name__ == "read":
        return ""
    while True:
        try:
            return func(*args)
        except OSError, e:
            if e.errno == errno.EINTR:
                continue
            raise
subprocess._eintr_retry_call = _eintr_retry_call
del _eintr_retry_call


def env2args(env):
    """Convert environment variables into make arguments."""
    for key, value in env.items():
        if value is True:
            yield "-D%s" % key
        else:
            yield "%s=%s" % (key, value)


def make_target(port, targets, pipe=None, **kwargs):
    """Build a make target and call a function when finished."""
    from .env import env as environ, env_master, flags

    if isinstance(port, str):
        assert pipe is True
        origin = port
    else:
        origin = port.origin

    if isinstance(targets, str):
        targets = (targets,)
    elif not isinstance(targets, tuple):
        targets = tuple(targets)

    env = {}
    env.update(environ)
    env.update(kwargs)

    args = ("make", "-C", os.path.join(env["PORTSDIR"], origin)) + targets
    for key, value in env_master.items():
        # Remove default environment variables
        if env[key] == value:
            del env[key]
    args += tuple(env2args(env))

    if flags["chroot"]:
        args = ("chroot", flags["chroot"]) + args

    if pipe is True:
        # Give access to subprocess output
        stdin, stdout, stderr = subprocess.PIPE, subprocess.PIPE, subprocess.PIPE
    elif pipe is False:
        # No piping of output (i.e. interactive)
        stdin, stdout, stderr = None, None, None
    elif not flags["no_op"]:
        # Pipe output to log_file
        stdin = subprocess.PIPE
        stdout = open(port.log_file, 'a')
        stderr = stdout
        stdout.write("# %s\n" % " ".join(args))

    if pipe is None and flags["no_op"]:
        make = PopenNone(args, port)
    else:
        make = Popen(args, port, stdin=stdin, stdout=stdout, stderr=stderr)
        if stdin is not None:
            make.stdin.close()

    return make


class Popen(subprocess.Popen, Signal):
    """A Popen class with signals that emits a signal on exit."""

    def __init__(self, target, origin, stdin, stdout, stderr):
        from .event import event

        subprocess.Popen.__init__(self, target, stdin=stdin, stdout=stdout,
                                  stderr=stderr, close_fds=True,
                                  preexec_fn=os.setsid)
        Signal.__init__(self, "Popen")
        self.origin = origin

        event(self, "p-").connect(self._emit)

    def _emit(self):
        """Emit signal after process termination."""
        self.emit(self)


class PopenNone(Signal):
    """An empty replacement for Popen."""

    returncode = SUCCESS  #: Return code for the dummy processes
    pid = None            #: PID of the dummy processes

    stdin  = None  #: Stdin stream
    stdout = None  #: Stdout stream
    stderr = None  #: Stderr stream

    def __init__(self, args, origin):
        from .env import flags
        from .event import post_event

        Signal.__init__(self)
        self.origin = origin
        if flags["no_op_print"]:
            print subprocess.list2cmdline(args)

        post_event(self.emit, self)

    def wait(self):
        """Simulate Popen.wait()."""
        return self.returncode
