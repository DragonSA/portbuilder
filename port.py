"""
The Port module.  This module contains all classes and utilities needed for
managing port information.  
"""

from __future__ import with_statement # Used for locking
from logging import getLogger
from make import env, make_target
from os import getenv

log = getLogger('pypkg.ports')

ports = {}  #: A cache of ports available with auto creation features
ports_dir = getenv("PORTSDIR", "/usr/ports/")  #: The location of the ports tree
ports_dir = env.get("PORTSDIR", ports_dir)
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

  ABSENT  = 0x01  #: Status flag for a port that is not installed
  OLDER   = 0x02  #: Status flag for a port that is old
  CURRENT = 0x04  #: Status flag for a port that is current
  NEWER   = 0x08  #: Status flag for a port that is newer

  CONFIG  = 0x01  #: Status flag for a port that is configuring
  FETCH   = 0x02  #: Status flag for a port that is fetching sources
  BUILD   = 0x04  #: Status flag for a port that is building
  INSTALL = 0x08  #: Status flag for a port that is installing
  DEPENDS = 0x10  #: Pseudo flag to indicate dependant failed

  INSTALL_NAME = {ABSENT : "Not Installed", OLDER : "Older",
                      CURRENT : "Current", NEWER : "Newer"}

  #: Translation table for the install flags
  STAGE_NAME = {CONFIG : "configure", FETCH : "fetch", BUILD : "build",
                INSTALL : "install"}
  #: Translation table for the build flags

  _log = getLogger("pypkg.port.Port")

  def __init__(self, origin):
    """
       Initialise the port and all its information

       @param origin: The ports origin (within the ports tree)
       @type origin: C{str}
    """
    self._origin = origin  #: The origin of the port
    self._install_status = port_status(origin) #: The install status of the port
    self._stage_status = 0  #: The (build) stage progress of the port
    self._attr_map = {}  #: The ports attributes
    self._working = False  #: Working flag
    self._failed = False  #: Failed flag

    if not port_filter & self._install_status:
      self._attr_map = port_attr(origin)

      def gen_method(name):
        ''' Generator: Create a method to retrieve attributes '''
        return lambda: self._attr_map[name]
      for i in self._attr_map.iterkeys():
        setattr(self, i, gen_method(i))

      if not self._attr_map['options']:
        self._stage_status = Port.CONFIG

  def attr(self):
    """
       Returns the ports attributes, such as version, categories, etc

       @return: The attributes
       @rtype: C{\{str:str|(str)|\}}
    """
    return self._attr_map

  def failed(self):
    """
       The failure status of this port.

       @return: The failed stage
       @rtype: C{bool}
    """
    return self._failed

  def install_status(self):
    """
       The install status of this port.

       @return: The install status
       @rtype: C{int}
    """
    return self._install_status

  def stage_status(self):
    """
       The (build) stage status of this port.

       @return: The build status
       @rtype: C{int}
    """
    stage_flag = 1
    while stage_flag <= self._stage_status:
      stage_flag <<= 1
    return stage_flag >> 1

  def working(self):
    """
       The working status of the port.
 
       @return: The build status
       @rtype: C{bool}
    """
    return self._working

  def config(self):
    """
       Configure the ports options.

       @return: The success status
       @rtype: C{bool}
    """
    if not self._prepare(Port.CONFIG):
      return False

    make = make_target(self._origin, 'config', pipe=False)
    status = make.wait() == 0

    if status:
      self._attr_map = port_attr(self._origin)

    return self._finalise(Port.CONFIG, status)

  def fetch(self):
    """
       Fetches the distribution files for this port

       @return: The success status
       @rtype: C{bool}
    """
    if not self._prepare(Port.FETCH):
      return False

    make = make_target(self._origin, 'checksum')
    return self._finalise(Port.FETCH, make.wait() == 0)

  def build(self):
    """
        Build the port.  This includes extracting, patching, configuring and
        lastly building the port.

        @return: The success status
        @rtype: C{bool}
    """
    if not self._prepare(Port.BUILD):
      return False

    make = make_target(self._origin, ['extract', 'patch', 'configure', 'build'])
    return self._finalise(Port.BUILD, make.wait() == 0)

  def install(self):
    """
        Install the port.

        @return: The success status
        @rtype: C{bool}
    """
    if not self._prepare(Port.INSTALL):
      return False

    make = make_target(self._origin, 'install')
    return self._finalise(Port.INSTALL, make.wait() == 0)

  def _prepare(self, stage):
    """
       Prepare the port to build the given stage.  All appropriate checks are
       done and the proceed status is returned.  If the stage can be built then
       the appropriate flags are tagged to indicated this.

       @param stage: The stage for which to prepare
       @type stage: C{int}
       @return: The proceed status
       @rtype: C{bool}
    """
    from queue import build_queue, fetch_queue
    if self._working:
      self._log.warn("Port '%s' is already busy and trying to start stage '%s'"
                     % (self._origin, Port.STAGE_NAME[stage]))
      return False
    if self._failed:
      self._log.warn("Port '%s' has failed but trying to start stage '%s'"
                     % (self._origin, Port.STAGE_NAME[stage]))
      return False

    queues = {Port.CONFIG : [build_queue, self.config],
              Port.FETCH  : [fetch_queue, self.fetch]}
    pre_stage = self.stage_status() << 1
    if pre_stage == 0:
      pre_stage = 1

    while pre_stage < stage:
      queue, func = queues[pre_stage]
      cond = queue.condition()

      queue.put([func])
      with cond:
        while not ((self._stage_status & pre_stage) and not self._working):
          cond.wait()

      if self._failed:
        self._log.warn("Port '%s' has failed but trying to start stage '%s'"
                     % (self._origin, Port.STAGE_NAME[stage]))
        return False
      pre_stage <<= 1

    self._stage_status |= stage
    self._working = True
    return True

  def _finalise(self, stage, status):
    """
       Finalise the port.  All appropriate flags are set given the status of
       this stage.

       @param stage: The stage for which to finalise
       @type stage: C{int}
       @param status: The status of this stage
       @type status: C{bool}
       @return: The status
       @rtype: C{bool}
    """
    self._working = False
    self._failed = not status
    if self._failed:
      self._log.error("Port '%s' has failed to complete stage '%s'"
                      % (self._origin, Port.STAGE_NAME[stage]))
    return status

class PortCache(dict):
  """
     The PortCache class.  This class keeps a cache of Port objects
     (note: this is an inflight cache)
  """

  _log = getLogger('pypkg.port.cache')  #: Logger for this cache

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

def port_attr(origin, change=False):
  """
     Retrieves the attributes for a given port

     @param origin: The port identifier
     @type origin: C{str}
     @param change: Indicates if the attributes have changed
     @type change: C{bool}
     @return: A dictionary of attributes
     @rtype: C{\{str:str|(str)|\}}
  """
  args = []
  for i in ports_attr.itervalues():
    args.append('-V')
    args.append(i[0])

  make = make_target(origin, None, args)
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
