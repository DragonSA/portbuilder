"""Support functions for debuging."""

__all__ = ["get_tb"]

def get_tb(offset=0):
  """Get the current traceback, excluding the top `offset` frames."""
  from .env import flags

  if flags["debug"]:
    from traceback import extract_stack
    return extract_stack()[:-(offset + 2)]
  else:
    return None
