"""Support functions for debuging."""

from __future__ import absolute_import

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
  from os.path import join
  from datetime import datetime
  from .env import flags

  fullmsg = "%s %s> %s\n" % (datetime.now(), func, "\t".join(msg))

  open(join(flags["log_dir"], flags["log_file"]), "a").write(fullmsg)

def exception():
  """Report an exception to the general logfile"""
  from datetime import datetime
  from os.path import join
  from traceback import format_list
  from .event import traceback
  from .env import flags

  log = open(join(flags["log_dir"], flags["log_file"]), "a")
  log.write("%s> EXCEPTION\n")
  for tb, name in traceback():
    log.write("\tTraceback from %s (most recent call last):\n" % name)
    log.write("%s\n" % "\t".join(format_list(tb)))
  log.close()
