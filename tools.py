from contextlib import contextmanager

@contextmanager
def invert(thing):
  thing.__exit__(None, None, None)
  yield thing
  thing.__enter__()

