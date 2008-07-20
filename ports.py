"""
The Port module.  This module contains all classes and utilities needed for
managing port information.  
"""

from __future__ import with_statement # Used for locking
from logging import getLogger

log = getLogger('pypkg.ports')

ports = {}  #: A cache of ports available with auto creation features
ports_dir = "/usr/ports/"  #: The location of the ports tree
port_filter = 0  #: The ports filter, if ports status matches then not 'loaded'

ports_attr = {
# Port naming
"name":     ["PORTNAME",     str], # The port's name
"version":  ["PORTVERSION",  str], # The port's version
"revision": ["PORTREVISION", str], # The port's revision
"epoch":    ["PORTEPOCH",    str], # The port's epoch

# Port's package naming
"pkgname": ["PKGNAME",       str], # The port's package name
"prefix":  ["PKGNAMEPREFIX", str], # The port's package prefix
"suffix":  ["PKGNAMESUFFIX", str], # The port's package suffix

# Port's dependancies and conflicts
"conflicts":      ["CONFLICTS",       tuple], # The port's conflictions
"depends":        ["_DEPEND_DIRS",    tuple], # The port's dependency list
"depend_build":   ["BUILD_DEPENDS",   tuple], # The port's build dependancies
"depend_extract": ["EXTRACT_DEPENDS", tuple], # The port's extract dependancies
"depend_fetch":   ["FETCH_DEPENDS",   tuple], # The port's fetch dependancies
"depend_lib":     ["LIB_DEPENDS",     tuple], # The port's library dependancies
"depend_run":     ["RUN_DEPENDS",     tuple], # The port's run dependancies
"depend_patch":   ["PATCH_DEPENDS",   tuple], # The port's patch dependancies

# Sundry port information
"categ":      ["CATEGORIES", tuple], # The port's categories
"comment":    ["COMMENT",    str],   # The port's comment
"maintainer": ["MAINTAINER", str],   # The port's maintainer
"options":    ["OPTIONS",    str],   # The port's options

# Distribution information
"distfiles": ["DISTFILES",   tuple], # The port's distfiles
"subdir":    ["DIST_SUBDIR", str],   # The port's distfile's sub-directory


"depends":  ["_DEPEND_DIRS", tuple], # The ports dependants
} #: The attributes of the given port

# The following are 'fixes' for various attributes
ports_attr["depends"].append(lambda x: [i[len(ports_dir):] for i in x])
ports_attr["depends"].append(lambda x: ([x.remove(i) for i in x
                                         if x.count(i) > 1], x)[1])
ports_attr["depends"].append(lambda x: [i for i in x if not ports.add(i)])
ports_attr["distfiles"].append(lambda x: [i.split(':', 1)[0] for i in x])

strip_depends = lambda x: [i.split(':', 1)[1][len(ports_dir):] for i in x]
ports_attr["depend_build"].append(strip_depends)
ports_attr["depend_extract"].append(strip_depends)
ports_attr["depend_fetch"].append(strip_depends)
ports_attr["depend_lib"].append(strip_depends)
ports_attr["depend_run"].append(strip_depends)
ports_attr["depend_patch"].append(strip_depends)

class Port(object):
  """
     The class that contains all information about a given port, such as status,
     dependancies and dependants
  """

  ABSENT    = 0x01  #: Status flag for a port that is not installed
  OLDER     = 0x02  #: Status flag for a port that is old
  CURRENT   = 0x04  #: Status flag for a port that is current
  NEWER     = 0x08  #: Status flag for a port that is newer

  CONFIGURE = 0x10  #: Status flag for a port that is configuring
  FETCH     = 0x20  #: Status flag for a port that is fetching sources
  BUILD     = 0x40  #: Status flag for a port that is building
  INSTALL   = 0x80  #: Status flag for a port that is installing

  INSTALL_STATUS = {ABSENT : "Not Installed", OLDER : "Older",
                      CURRENT : "Current", NEWER : "Newer"}
  BUILD_STATUS   = {CONFIGURE : "Configuring", FETCH : "Fetching",
                    BUILD : "Building", INSTALL : "Installing"}

  def __init__(self, origin):
    """
       Initialise the port and all its information

       @param origin: The ports origin (within the ports tree)
       @type origin: C{str}
    """
    self._origin = origin  #: The origin of the port
    self._status = port_status(origin)  #: The status of the port
    self._attr_map = {}  #: The ports attributes

    if not port_filter & self._status:
      self._attr_map = port_attr(origin)  #: The ports attributes
      self._gen_attr()

  def _gen_attr(self):
    """
       Generates methods that map to the ports attributes
    """
    def gen_method(name):
      ''' Generator: Create a method to retrieve attributes '''
      return lambda: self._attr_map[name]
    for i in self._attr_map.iterkeys():
      setattr(self, i, gen_method(i))

  def attr(self):
    """
       Returns the ports attributes, such as version, categories, etc

       @return: The attributes
       @rtype: C{\{str:str|(str)|\}}
    """
    return self._attr_map

  def status(self, string=False):
    """
       Returns the status of the port, either as a number or a string

       @param string: Wheather to return a string or number
       @type string: C{bool}
       @return: The ports status
       @rtype: C{int} or C{bool}
    """
    if not string:
      return self._status
    else:
      if Port.BUILD_STATUS.has_key(self._status & 0xf0):
        return "%s and %s" % (Port.INSTALL_STATUS[self._status & 0x0f],
                              Port.BUILD_STATUS[self._status & 0xf0])
      else:
        return Port.INSTALL_STATUS[self._status & 0x0f]

class PortCache(dict):
  """
     The PortCache class.  This class keeps a cache of Port objects
     (note: this is an inflight cache)
  """

  _log = getLogger('pypkg.ports.cache')  #: Logger for this cache

  def __init__(self):
    """
       Initialise the cache of ports
    """
    dict.__init__(self)

    from threading import Lock
    self._lock = Lock()

  def __getitem__(self, key):
    """
       Retrieve a port by name.  If the work does not exist then it is queued
       for construction.  The method waits for the port to be constructed then
       returns the port

       @param key: The port to retrieve
       @type key: C{str}
       @return: The port requested
       @rtype: C{Port}
    """
    from queue import ports_queue

    with self._lock:
      try:
        value = dict.__getitem__(self, key)
        if value:
          return value
      except KeyError:
        self._add(key)
        value = None
      else:
        if value == False:
          raise KeyError, key

      self._lock.release()
      cond = ports_queue.condition()
      with cond:
        while True:
          value = dict.__getitem__(self, key)
          if value == False:
            self._lock.acquire()
            raise KeyError, key
          elif not value:
            cond.wait()
          else:
            self._lock.acquire()
            return value

  def __setitem__(self, key, value):
    """
       Records a port in the cache

       @param key: The ports name
       @type key: C{str}
       @param value: The port object
       @type value: C{str}
    """
    with self._lock:
      dict.__setitem__(self, key, value)

  def _add(self, key):
    """
       Adds a port to be contructed if not already in the cache or queued for
       construction

       @param key: The port for queueing
       @type key: C{str}
    """
    from queue import ports_queue
    if not self.has_key(key):
      dict.__setitem__(self, key, None)
      ports_queue.put_nowait((self.get, [key]))

  def add(self, key):
    """
       Adds a port to be contructed if not already in the cache or queued for
       construction

       @param key: The port for queueing
       @type key: C{str}
    """
    with self._lock:
      self._add(key)

  def get(self, k):
    """
       Get a port.  If the port is not in the cache then created it (whereas
       __getitem__ would queue the port to be constructed).  Use this if the
       port requested is a once of request

       @param k: The port to get
       @type k: C{str}
       @return: The port
       @rtype: C{Port}
    """
    with self._lock:
      try:
        value = dict.__getitem__(self, k)
        if value:
          return value
      except KeyError:
        dict.__setitem__(self, k, None)
      else:
        if value == False:
          raise KeyError, k

    try:
      # Time consuming task, done outside lock
      port = Port(k)
    except BaseException:
      with self._lock:
        dict.__setitem__(self, k, False)
        self._log.exception("Error while creating port '%s'" % k)
        raise KeyError, k
    else:
      with self._lock:
        value = dict.__getitem__(self, k)
        if not value:
          dict.__setitem__(self, k, port)
          value = port
          self._log.info("Duplicate port '%s' detected" % k)
        return value

ports = PortCache()

def port_status(origin):
  """
     Get the current status of a port.  A port is either ABSENT, OLDER, CURRENT
     or NEWER

     @param origin: The origin of the port queried
     @type origin: C{str}
     @return: The port's status
     @rtype: C{int}
  """
  from subprocess import Popen, PIPE, STDOUT
  pkg_version = Popen(['pkg_version', '-O', origin], stdout=PIPE, stderr=STDOUT)
  if pkg_version.wait() != 0:
    return Port.ABSENT

  info = pkg_version.stdout.read().split()
  if len(info) > 2:
    log.warning("Multiple ports with same origin '%s'" % origin)
  info = info[1]
  if info == '<':
    return Port.OLDER
  elif info == '>':
    return Port.NEWER
  else: #info == '=' or info == '?' or info =='*'
    return Port.CURRENT

def port_attr(origin):
  """
     Retrieves the attributes for a given port

     @param origin: The port identifier
     @type origin: C{str}
     @return: A dictionary of attributes
     @rtype: C{\{str:str|(str)|\}}
  """
  from subprocess import Popen, PIPE, STDOUT

  args = ['make', '-C', ports_dir + origin]
  for i in ports_attr.itervalues():
    args.append('-V')
    args.append(i[0])

  make = Popen(args, stdout=PIPE, stderr=STDOUT)
  if make.wait() > 0:
    log.info("Error in obtaining information for port '%s'" % origin)
    return {}

  attr_map = {}
  for name, value in ports_attr.iteritems():
    if value[1] == str:
      attr_map[name] = make.stdout.readline().strip()
    else:
      attr_map[name] = value[1](make.stdout.readline().split())
    for i in value[2:]:
      attr_map[name] = i(attr_map[name])

  return attr_map
