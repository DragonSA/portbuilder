"""
The Tools module.  This module contains various utilities (that should be in
the standard libraries) for ease of programming...
"""

from contextlib import contextmanager

@contextmanager
def invert(thing):
  """
     Invert the order applied to an object.

     @param thing: The object to invert
  """
  thing.__exit__(None, None, None)
  yield thing
  thing.__enter__()

# TODO: To be moved in with PortCache (or Port)
recurse_depends_cache = dict()  #: Default recurse_depends' cache
def recurse_depends(port, category, cache=recurse_depends_cache):
  """
     Returns a sorted list of dependancies pkgname.  Only the categories are
     evaluated.

     @param port: The port the dependancies are for.
     @type port: C{Port}
     @param category: The dependancies to retrieve.
     @type category: C{(str)}
     @param cache: Use the given cache to increase speed
     @type cache: C{\{str:(str)\}}
     @return: A sorted list of dependancies
     @rtype: C{str}
  """
  master = ('depend_lib', 'depend_run')
  def retrieve(port, categories):
    """
       Get the categories for the port

       @param port: The port the dependancies are for.
       @type port: C{Port}
       @param category: The dependancies to retrieve.
       @type category: C{(str)}
       @return: The sorted list of dependancies
       @rtype: C{(str)}
    """
    from port import port_cache

    depends = set()
    for i in set([j[1] for j in sum([port.attr(i) for i in categories], [])]):
      i_p = port_cache.get(i)
      if i_p:
        depends.add(i_p.attr('pkgname'))
        depends.update(cache.has_key(i) and cache[i] or retrieve(i_p, master))
      else:
        from logging import getLogger
        getLogger('pypkg.recurse_depends').warn("Port '%s' has a " \
                  "(indirect) stale dependancy on '%s'" % (port.origin(), i))

    depends = list(depends)
    depends.sort()

    if set(category) == set(master):
      cache[port.origin()] = tuple(depends)

    return depends

  if set(category) == set(master) and cache.has_key(port.origin()):
    return " ".join(cache[port.origin()])

  return " ".join(retrieve(port, category))

def run_main(main):
  """
     Run the main function in its own thread and then runs the exit handler
     function.  This function does not return.

     @param main: The main function to execute
     @type main: C{callable}
  """
  from exit import exit_handler, terminate
  from threading import Thread

  assert callable(main)

  def call():
    """
       Call the main function and then start the idle checker.
    """
    try:
      main()
    except SystemExit:
      terminate()
    except BaseException:
      from logging import getLogger
      getLogger("pypkg").exception("Main function failed")
      terminate()
    finally:
      exit_handler.start()

  Thread(target=call).start()
  exit_handler.run()
