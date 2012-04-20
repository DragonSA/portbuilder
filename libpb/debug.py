"""The logging module.  This module provides support for logging messages."""

from __future__ import absolute_import, with_statement

import datetime
import os
import traceback

from libpb import env, event

__all__ = ["debug", "error", "exception", "get_tb"]


def get_tb(offset=0):
    """Get the current traceback, excluding the top `offset` frames."""
    if env.flags["debug"]:
        return traceback.extract_stack()[:-(offset + 2)]
    else:
        return None


def format_tb(tb, name):
    msg = "Traceback from %s (most recent call last):\n" % name
    msg += "%s\n" % "".join(traceback.format_list(tb))
    return msg


def logfile():
    return os.path.join(env.flags["log_dir"], env.flags["log_file"])


def debug(func, msg):
    msg = "\n".join(msg)
    if env.flags["debug"]:
        msg = msg.replace("\n", "n  ")
        msg = "%s %s> %s\n" % (datetime.datetime.now(), func, msg)
        with open(logfile(), "a") as log:
            log.write(msg)


def error(func, msg, trace=False):
    """Report an error to the general logfile"""
    fullmsg = "%s %s> %s\n" % (datetime.datetime.now(), func, "\n  ".join(msg))
    if trace and env.flags["debug"]:
        msg = "  "
        msg += "".join(format_tb(tb, name) for tb, name in event.traceback() if tb)
        msg += format_tb(get_tb(), "message")
        fullmsg += msg.replace("\n", "\n  ")[:-2]

    with open(logfile(), "a") as log:
        log.write(fullmsg)


def exception():
    """Report an exception to the general logfile"""
    msg = "  "
    msg += "".join(format_tb(tb, name) for tb, name in event.traceback() if tb)
    msg += traceback.format_exc()
    msg += "\n"
    with open(logfile(), "a") as log:
        log.write("%s> EXCEPTION\n" % datetime.datetime.now())
        log.write(msg.replace("\n", "\n  ")[:-2])
