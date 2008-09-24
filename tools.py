"""
The Tools module.  This module contains various utilities (that should be in
the standard libraries) for ease of programming...
"""

from contextlib import contextmanager

@contextmanager
def invert(thing):
  """
     Invert the order applied to an object

     @param thing: The object to invert
  """
  thing.__exit__(None, None, None)
  yield thing
  thing.__enter__()

