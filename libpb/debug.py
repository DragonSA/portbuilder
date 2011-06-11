"""Support functions for debuging."""

from __future__ import absolute_import

import datetime
import os
import traceback

__all__ = ["error", "exception", "get_tb"]

def get_tb(offset=0):
  """Get the current traceback, excluding the top `offset` frames."""
  from .env import flags

  if flags["debug"]:
    from traceback import extract_stack
    return extract_stack()[:-(offset + 2)]
  else:
    return None

def error(func, msg):
  """Report an error to the general logfile"""
  from .env import flags

  fullmsg = "%s %s> %s\n" % (datetime.datetime.now(), func, "\n  ".join(msg))

  open(os.path.join(flags["log_dir"], flags["log_file"]), "a").write(fullmsg)

def exception():
  """Report an exception to the general logfile"""
  from .event import traceback as event_traceback
  from .env import flags

  log = open(os.path.join(flags["log_dir"], flags["log_file"]), "a")
  log.write("%s> EXCEPTION\n  " % datetime.datetime.now())
  msg = ""
  for tb, name in event_traceback():
    msg += "Traceback from %s (most recent call last):\n" % name
    msg += "%s\n" % "".join(traceback.format_list(tb))
  msg += traceback.format_exc()
  log.write(msg.replace("\n", "\n  "))
  log.close()
