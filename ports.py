"""
The library of the port class and all related functions.
"""

portsdir = "/usr/ports/"  #: The location of the ports tree

def Port(object):
  """
     The class that contains all information about a given port, such as status,
     dependancies and dependants
  """

  def __init__(self, origin):
    """
       Initialise the port and all its information

       @param origin: The ports origin (within the ports tree)
       @type origin: C{str}
    """
    self.origin = origin               #: The origin of the port
    self.depends = get_depends(origin)  #: A list of all dependancies (Port's)

def get_depends(origin):
  """
     Retrieve a list of dependants given the ports origin

     @param origin: The port identifier
     @type origin: C{str}
     @return: A list of dependentant ports
     @rtype: C{[Port]}
  """
  from popen import Popen, PIPE

  make = Popen(['make', '-C', portsdir + origin, '-V', '_DEPEND_DIRS'],
               stdout=PIPE)
  make.wait()
  depends = [i[len(portsdir):] for i in make.stdout.read().split()]
  return ports_cache.get_all(depends)
