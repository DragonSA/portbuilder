"""The logging module.  This module provides support for logging messages."""

from __future__ import absolute_import, with_statement

import datetime
import os
import time
import traceback

from libpb import env

__all__ = ["debug", "error", "exception", "get_tb"]

start_time = time.time()


def get_tb(offset=0):
    """Get the current traceback, excluding the top `offset` frames."""
    if env.flags["debug"]:
        return traceback.extract_stack()[:-(offset + 2)]
    else:
        return None


def format_tb(tb, name):
    if tb is None:
        return ""
    msg = "Traceback from %s (most recent call last):\n" % name
    msg += "%s\n" % "".join(traceback.format_list(tb))
    return msg


def logfile():
    return os.path.join(env.flags["log_dir"], env.flags["log_file"])


def offset_time():
    return time.time() - start_time


def debug(func, msg):
    if env.flags["debug"]:
        msg = msg.replace("\n", "n  ")
        msg = "[%10.3f] (D) %s> %s\n" % (offset_time(), func, msg)
        with open(logfile(), "a") as log:
            log.write(msg)


def error(func, msg, trace=False):
    """Report an error to the general logfile"""
    msg = msg.replace("\n", "n  ")
    fullmsg = "[%10.3f] (E) %s> %s\n" % (offset_time(), func, msg)
    if trace and env.flags["debug"]:
        from libpb import event
        msg = "  "
        msg += "".join(format_tb(tb, name) for tb, name in event.traceback())
        msg += format_tb(get_tb(), "message")
        fullmsg += msg.replace("\n", "\n  ")[:-2]

    with open(logfile(), "a") as log:
        log.write(fullmsg)


def exception():
    """Report an exception to the general logfile"""
    from libpb import event
    msg = "  "
    msg += "".join(format_tb(tb, name) for tb, name in event.traceback())
    msg += traceback.format_exc()
    msg += "\n"
    with open(logfile(), "a") as log:
        log.write("[%10.3f] (EXCEPTION)\n" % (offset_time()))
        log.write(msg.replace("\n", "\n  ")[:-2])
