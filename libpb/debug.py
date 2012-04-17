"""Support functions for debuging."""

from __future__ import absolute_import

import datetime
import os
import traceback

from libpb import env

__all__ = ["error", "exception", "get_tb"]


def get_tb(offset=0):
    """Get the current traceback, excluding the top `offset` frames."""
    from .env import flags

    if flags["debug"]:
        from traceback import extract_stack
        return extract_stack()[:-(offset + 2)]
    else:
        return None


def error(func, msg, trace=False):
    """Report an error to the general logfile"""
    from .env import flags

    fullmsg = "%s %s> %s\n" % (datetime.datetime.now(), func, "\n  ".join(msg))

    open(os.path.join(flags["log_dir"], flags["log_file"]), "a").write(fullmsg)

    if trace and env.flags["debug"]:
        from .event import traceback as event_traceback
        from .env import flags

        log = open(os.path.join(flags["log_dir"], flags["log_file"]), "a")
        msg = "  "
        for tb, name in event_traceback() + [(get_tb(), "message")]:
            msg += "Traceback from %s (most recent call last):\n" % name
            msg += "%s\n" % "".join(traceback.format_list(tb))
        log.write(msg.replace("\n", "\n  ")[:-2])
        log.close()


info = error
debug = error


def exception():
    """Report an exception to the general logfile"""
    from .event import traceback as event_traceback
    from .env import flags

    log = open(os.path.join(flags["log_dir"], flags["log_file"]), "a")
    log.write("%s> EXCEPTION\n" % datetime.datetime.now())
    msg = "  "
    for tb, name in event_traceback():
        msg += "Traceback from %s (most recent call last):\n" % name
        msg += "%s\n" % "".join(traceback.format_list(tb))
    msg += traceback.format_exc()
    msg += "\n"
    log.write(msg.replace("\n", "\n  ")[:-2])
    log.close()
