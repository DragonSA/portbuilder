"""
The Hacks module.  This module overrides system operations to patch errors or
to enhance functionality.  This should be imported once and only once (and
before any threading operations take place, preferably before 'threading' or
'thread' is imported)
"""
from __future__ import with_statement

if not locals().has_key('hacks_finished'):

  register_db = []
  def register(module, attribute, override, locked=False):
    """
       Register an override and keep a track of all overrides.

       @param module: The module name
       @type module: C{str}
       @param attribute: The attribute to override
       @type attribute: C{str}
       @param override: The object to override with
       @type override: C{object}
       @param locked: If the override object requires a lock
       @type locked: C{bool}
    """
    try:
      mod = __import__(module)
      attr = getattr(mod, attribute)
    except ImportError:
      print "Failed to import module '%s' for override of attribute '%s'" \
            % (module, attribute)
      return
    except AttributeError:
      print "Failed to get attribute '%s' of module '%s' for override" \
            % (module, attribute)
      return

    override.this = attr
    if locked:
      import thread
      lock = thread.allocate_lock()
      override.lock = lock
    setattr(mod, attribute, override)
    register_db.append((mod, attr, override))

  lock_store = []
  def allocate_lock():
    """
       Keep a track of all locks created.  This is useful as both a cache and
       for cleaning up locks, when needed... (See fork below)

       @return: The lock object
       @rtype: C{thread.lock}
    """
    from sys import getrefcount

    with allocate_lock.lock:
      # Since we keep a record of all the locks we need to tidy up when the
      # locks become free
      for i in xrange(len(lock_store) - 1, -1, -1):
        if getrefcount(lock_store[i]) <= 2:
          # Make sure the lock has been released before we delete it
          if lock_store[i].locked():
            lock_store[i].release()
          lock_store.pop(i)

      lock = allocate_lock.this()
      lock_store.append(lock)
      return lock

  def fork():
    """
       Ensure all locks are free in the child process

       @return: The pid of the child, or 0 if we are the child
       @rtype: C{int}
    """
    pid = fork.this()
    if not pid:
      global lock_store
      # Free all the locks.
      for i in lock_store:
        if i.locked() and i is not allocate_lock.lock:
          i.release()
      del lock_store
      lock_store = []
    return pid

  def popen(*args, **kwargs):
    """
       Ensure Popen is called at most once concurrently and make close_fds
       default to True.

       @param args: Tuple of arguments for Popen
       @type args: C{(...)}
       @param kwargs: Dictionary of arguments for Popen
       @type kwargs: C{\{...\}}
       @return: The Popen object
       @rtype: C{subprocess.Popen}
    """
    # Make close_fds=True the default.  Fixes some deadlocking bugs
    #if len(args) < 7 and not kwargs.has_key("close_fds"):
      #kwargs["close_fds"] = True

    with popen.lock:
      return popen.this(*args, **kwargs)

  register("thread", "allocate_lock", allocate_lock, locked=True)
  register("os", "fork", fork)
  register("subprocess", "Popen", popen, locked=True)

# Safeguard, must only be imported once
hacks_finished = True
