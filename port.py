"""
The Port module.  This module contains all classes and utilities needed for
managing port information.  
"""
from __future__ import with_statement

from make import env

port_cache = {}  #: A cache of ports available with auto creation features

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
"category":   ["CATEGORIES", tuple], # The port's categories
"descr":      ["_DESCR",     str],   # The port's description file
"comment":    ["COMMENT",    str],   # The port's comment
"maintainer": ["MAINTAINER", str],   # The port's maintainer
"options":    ["OPTIONS",    str],   # The port's options
"prefix":     ["PREFIX",     str],   # The port's install prefix

# Distribution information
"distfiles": ["DISTFILES",   tuple], # The port's distfiles
"subdir":    ["DIST_SUBDIR", str],   # The port's distfile's sub-directory

"depends":  ["_DEPEND_DIRS", tuple], # The ports dependants
} #: The attributes of the given port

# The following are 'fixes' for various attributes
ports_attr["depends"].append(lambda x: [i[len(env['PORTSDIR']):] for i in x])
ports_attr["depends"].append(lambda x: ([x.remove(i) for i in x
                                         if x.count(i) > 1], x)[1])
ports_attr["distfiles"].append(lambda x: [i.split(':', 1)[0] for i in x])

strip_depends = lambda x: [(i.split(':', 1)[0].strip(),
                  i.split(':', 1)[1][len(env['PORTSDIR']):].strip()) for i in x]
ports_attr["depend_build"].append(strip_depends)
ports_attr["depend_extract"].append(strip_depends)
ports_attr["depend_fetch"].append(strip_depends)
ports_attr["depend_lib"].append(strip_depends)
ports_attr["depend_run"].append(strip_depends)
ports_attr["depend_patch"].append(strip_depends)

del strip_depends

class Port(object):
  """
     The class that contains all information about a given port, such as status,
     dependancies and dependants
  """
  from logging import getLogger
  from threading import Condition, Lock

  ABSENT  = 0  #: Status flag for a port that is not installed
  OLDER   = 1  #: Status flag for a port that is old
  CURRENT = 2  #: Status flag for a port that is current
  NEWER   = 3  #: Status flag for a port that is newer

  CONFIG  = 1  #: Status flag for a port that is configuring
  FETCH   = 2  #: Status flag for a port that is fetching sources
  BUILD   = 3  #: Status flag for a port that is building
  INSTALL = 4  #: Status flag for a port that is installing

  #: Translation table for the install flags
  INSTALL_NAME = {ABSENT : "Not Installed", OLDER : "Older",
                  CURRENT : "Current", NEWER : "Newer"}

  #: Translation table for the build flags
  STAGE_NAME = {CONFIG : "configure", FETCH : "fetch", BUILD : "build",
                INSTALL : "install"}

  configure = True  #: If the port should configure itself
  fetch_only = False  #: Only fetch the port, skip all other stages
  package = False  #: If newly installed ports should be packaged

  _log = getLogger("pypkg.port")
  _lock = Condition(Lock())  #: The notifier and locker for all ports

  def __init__(self, origin):
    """
       Initialise the port and all its information

       @param origin: The ports origin (within the ports tree)
       @type origin: C{str}
    """
    self._origin = origin  #: The origin of the port
    self._install_status = port_status(origin) #: The install status of the port
    self._stage = 0  #: The (build) stage progress of the port
    self._attr_map = {}  #: The ports attributes
    self._working = False  #: Working flag
    self._failed = False  #: Failed flag
    self._depends = None  #: The dependant handlers for various stages

    self._attr_map = port_attr(origin)

    for i in self._attr_map['depends']:
      port_cache.add(i)

  def attr(self, attr):
    """
       Returns the ports attributes, such as version, categories, etc

       @param attr: The port attribute to retrieve
       @type attr: C{str}
       @return: The attributes
       @rtype: C{str|(str)}
    """
    try:
      return self._attr_map[attr]
    except KeyError:
      # Silent failure, may be acceptable at times?
      self._log.exception("Port attribute key error: ``%s''" % attr)
      return ''

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

  def lock(self):
    """
       The lock this port uses

       @return: The ports lock
       @rtype: C{Lock}
    """
    return self._lock

  def stage(self):
    """
       The currently (building or completed) stage

       @return: The build status
       @rtype: C{int}
    """
    return self._stage

  def origin(self):
    """
       The origin of this port

       @return: The ports origin
       @rtype: C{int}
    """
    return self._origin

  def working(self):
    """
       The working status of the port.

       @return: The build status
       @rtype: C{bool}
    """
    return self._working

  def depends(self):
    """
       Returns the dependant handler for this port

       WARNING: Dead lock will occure if there is a cyclic port dependancy

       @return: The dependant handler
       @rtype: C{DependHandler}
    """
    if self._depends:
      return self._depends

    with self._lock:
      while self._depends is False:
        self._lock.wait()

      if not self._depends:
        if not self._failed:
          self._depends = False
        else:
          self._depends = DependHandler(self)

    if self._depends:
      return self._depends

    if self._stage < Port.CONFIG:
      self.config()

    depends_obj = DependHandler(self, [self.attr(i) for i in
                  ('depend_build', 'depend_extract', 'depend_fetch',
                   'depend_lib',   'depend_run',     'depend_patch')])

    with self._lock:
      self._depends = depends_obj
      self._lock.notifyAll()

    return self._depends

  def describe(self):
    """
       Creates a one line string that describes the port.  The following format
       is used:
         ${PKGNAME}|${PORTDIR}/${ORIGIN}|${PREFIX}|${COMMENT}|${DESCR_FILE}|
         ${MAINTAINER}|${CATEGORIES}|${BUILD_DEPENDS}|${RUN_DEPENDS}|
         ${WWW_SITE}|${EXTRACT_DEPENDS}|${PATCH_DEPENDS|${FETCH_DEPENDS}

       @return: A one line description of this port
       @rtype: C{str}
    """
    from os.path import join

    def get_www():
      """
         Get the WWW address in the description file

         @return: The WWW URL
         @rtype: C{str}
      """
      from os.path import isfile

      descr = self.attr('descr')
      if isfile(descr):
        for i in open(descr, 'r'):
          i = i.strip()
          if i.startswith('WWW:'):
            www = i[4:].lstrip()
            if www.split('://', 1)[0] in ('http', 'https', 'ftp'):
              return www
            return 'http://' + www
      else:
        self._log.warn("Invalid description file for '%s'" % self._origin)
      return ''

    build_depends = ('depend_build', 'depend_lib')
    extract_depends = ('depend_extract',)
    fetch_depends = ('depend_fetch',)
    patch_depends = ('depend_patch',)
    run_depends = ('depend_lib', 'depend_run')

    return "|".join((
           self.attr('pkgname'),                          # ${PKGNAME}
           join(env['PORTSDIR'], self._origin),           # ${PORTDIR}/${ORIGIN}
           self.attr('prefix'),                           # ${PREFIX}
           self.attr('comment'),                          # ${COMMENT}
           self.attr('descr'),                            # ${DESCR_FILE}
           self.attr('maintainer'),                       # ${MAINTAINER}
           " ".join(self.attr('category')),               # ${CATEGORIES}
           self.__recurse_depends(self, build_depends),   # ${BUILD_DEPENDS}
           self.__recurse_depends(self, run_depends),     # ${RUN_DEPENDS}
           get_www(),                                     # ${WWW_SITE}
           self.__recurse_depends(self, extract_depends), # ${EXTRACT_DEPENDS}
           self.__recurse_depends(self, patch_depends),   # ${PATCH_DEPENDS}
           self.__recurse_depends(self, fetch_depends),   # ${FETCH_DEPENDS}
           )) 

  def clean(self):
    """
       Clean the ports working directories

       @return: The clean status
       @rtype: C{bool}
    """
    from make import clean_log, make_target, SUCCESS

    status = make_target(self._origin, ['clean']).wait() is SUCCESS

    if not self._failed:
      clean_log(self._origin)

    # Do some checks, to make sure we are in the correct state
    with self._lock:
      if not self._failed and self._stage > Port.FETCH and \
          (self._stage != Port.INSTALL or self._working):
        self._stage = Port.FETCH
        self._working = False
      elif self._stage in (Port.CONFIG, Port.FETCH):
        self._failed = True

    return status

  def build_stage(self, stage, queue=True):
    """
       Generic handler for building a stage, this calls the correct method.
       This does not add the port to the construction queue and should only
       be called by the correstonding _builder (Note: private but friendly C++)

       @param stage: The stage to build
       @type stage: C{int}
       @return: The stage result
       @rtype: C{bool}
    """
    from target import config_builder, fetch_builder, build_builder, \
                       install_builder
    stage_handler = {Port.CONFIG: self._config, Port.FETCH: self._fetch,
                     Port.BUILD: self._build, Port.INSTALL: self._install}
    stage_builder = {Port.CONFIG: config_builder, Port.FETCH: fetch_builder,
                     Port.BUILD: build_builder, Port.INSTALL: install_builder}
    assert (queue and stage_builder.has_key(stage)) or \
           (not queue and stage_handler.has_key(stage))

    if queue:
      with self._lock:
        if self._failed:
          return False
        elif self._stage > stage:
          return True

      stage_builder[stage](self)

      with self._lock:
        while (self._stage < stage or (self._working and self._stage == stage))\
              and not self._failed:
          self._lock.wait()

        return self._failed
    else:
      proceed, status = self._prepare(stage)
      if not proceed:
        return status

      status = stage_handler[stage]()

      return self._finalise(stage, status)

  config = lambda self: self.build_stage(Port.CONFIG)
  def _config(self):
    """
       Configure the ports options.

       @return: The success status
       @rtype: C{bool}
    """
    from make import make_target, SUCCESS

    if len(self._attr_map['options']) == 0 or not Port.configure:
      return True
    else:
      make = make_target(self._origin, 'config', pipe=False)
      status = make.wait() is SUCCESS

      if status:
        self._attr_map = port_attr(self._origin)
        for i in self._attr_map['depends']:
          port_cache.add(i)

      return status

  fetch = lambda self: self.build_stage(Port.FETCH)
  def _fetch(self):
    """
       Fetches the distribution files for this port

       @return: The success status
       @rtype: C{bool}
    """
    from make import make_target, SUCCESS

    return make_target(self._origin, ['checksum']).wait() is SUCCESS

  build = lambda self: self.build_stage(Port.BUILD)
  def _build(self):
    """
        Build the port.  This includes extracting, patching, configuring and
        lastly building the port.

        @return: The success status
        @rtype: C{bool}
    """
    from make import make_target, SUCCESS

    #make = make_target(self._origin, ['extract','patch','configure','build'])
    make = make_target(self._origin, ['all'])
    return make.wait() is SUCCESS

  install = lambda self: self.build_stage(Port.INSTALL)
  def _install(self):
    """
        Install the port.

        @return: The success status
        @rtype: C{bool}
    """
    from make import make_target, SUCCESS

    make = make_target(self._origin, ['install'] +
                       (self.package and ['package'] or []))

    status = Port.INSTALL, make.wait() is SUCCESS
    if status:
      #  Don't need to lock to change this as it will already have been set
      self._install_status = Port.CURRENT
      self._depends.status_changed()

    return status

  def _prepare(self, stage):
    """
       Prepare the port to build the given stage.  All appropriate checks are
       done and the proceed status is returned.  If the stage can be built then
       the appropriate flags are tagged to indicated this.

       @param stage: The stage for which to prepare
       @type stage: C{int}
       @return: The proceed status (and succes status)
       @rtype: C{bool}
    """
    from time import time
    
    with self._lock:
      if self._stage > stage:
        return False, True

      while self._working:
        self._lock.wait()
        if not self._working and not self._failed and self._stage >= stage:
          return False, True

      if self._failed:
        return False, False

      if self._stage == stage or (Port.fetch_only and stage > Port.FETCH):
        self._stage = stage
        return False, True

      assert self._stage == stage - 1 and not self._failed

      self._stage = stage

      status = stage > Port.CONFIG and self.depends().check(stage) or \
               DependHandler.RESOLV
      if status is DependHandler.UNRESOLV:
        self._failed = True
        try:
          self._lock.release()
          self._depends.status_changed()
        finally:
          self._lock.acquire()
        return False, False

      self._working = time()

      return True, True

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
    assert self._working and not self._failed

    with self._lock:
      self._working = False
      if self._failed != (not status):
        self._failed = not status
        try:
          self._lock.release()
          self._depends.status_changed()
        finally:
          self._lock.acquire()
      self._lock.notifyAll()

    if self._failed and self._stage > Port.FETCH or self._stage == Port.INSTALL:
      self.clean()

    if self._failed:
      self._log.error("Port '%s' has failed to complete stage '%s'"
                      % (self._origin, Port.STAGE_NAME[stage]))
    return status

  def __recurse_depends(self, port, category, cache=dict()):
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
      depends = set()
      for i in set([j[1] for j in sum([port.attr(i) for i in categories], [])]):
        i_p = port_cache.get(i)
        if i_p:
          depends.add(i_p.attr('pkgname'))
          depends.update(cache.has_key(i) and cache[i] or retrieve(i_p, master))
        else:
          self._log.warn("Port '%s' has a (indirect) stale dependancy " \
                        "on '%s'" % (port.origin(), i))

      depends = list(depends)
      depends.sort()

      if set(category) == set(master):
        cache[port.origin()] = tuple(depends)

      return depends

    if set(category) == set(master) and cache.has_key(port.origin()):
      return " ".join(cache[port.origin()])
    return " ".join(retrieve(port, category))


class DependHandler(object):
  """
     The DependHandler class.  This class handles tracking the dependants
     and dependancies of a Port
  """
  from logging import getLogger
  from threading import RLock

  # The type of dependancies
  BUILD   = 0  #: Build dependants
  EXTRACT = 1  #: Extract dependants
  FETCH   = 2  #: Fetch dependants
  LIB     = 3  #: Library dependants
  RUN     = 4  #: Run dependants
  PATCH   = 5  #: Patch dependants

  # The dependancy status
  FAILURE    = -1  #  The port failed and cannot resolve the dependancy
  UNRESOLV   = 0   #: Either port is not installed or completely out of date
  PARTRESOLV = 1   #: Partly resolved, some dependancies not happy
  RESOLV     = 2   #: Dependancy resolved

  STAGE2DEPENDS = {
    Port.CONFIG:  (),                           # The config dependancies
    Port.FETCH:   (FETCH),                      # The fetch dependancies
    Port.BUILD:   (EXTRACT, PATCH, LIB, BUILD), # The build dependancies
    Port.INSTALL: (LIB, RUN),                   # The install dependancies
  } #: The dependancies for a given stage

  _lock = RLock()
  _log = getLogger("pypkg.depend_handler")

  def __init__(self, port, depends=None):
    """
       Initialise the databases of dependancies

       @param port: The port this is a dependant handler for
       @type port: Port
       @param depends: A list of the dependancies
       @type depends: C{[[(str, str)]]}
    """
    self._count = 0  #: The count of outstanding dependancies
    self._dependancies = [[], [], [], [], [], []]  #: All dependancies
    self._dependants   = [[], [], [], [], [], []]  #: All dependants
    self._port = port  #: The port whom we handle
    self._report_log = []  #: Log of all problems reported (to prevent dups)
    # TODO: Change to actually check if we are resolved
    # Port._install depends on install_status having been called here
    if port.install_status() > Port.ABSENT:
      self._status = DependHandler.RESOLV
    else:
      self._status = DependHandler.UNRESOLV

    if not depends:
      depends = [[]]
    elif len(depends) != len(self._dependancies):
      self._log.warn("Incomplete list of dependancies passed")

    for i in range(len(depends)):
      for j in depends[i]:
        self.add_dependancy(j[0], j[1], i)

  def add_dependancy(self, field, port, typ):
    """
       Add a dependancy to our list

       @param field: The field data for the dependancy
       @type field: C{str}
       @param port: The dependant
       @type port: C{str}
       @param typ: The type of dependancy
       @type typ: C{int}
    """
    try:
      depends = port_cache[port].depends()
    except KeyError:
      ports_msg = (self._port.origin(), port)
      if ports_msg not in self._report_log:
        self._log.error("Port '%s' has a stale dependancy on port '%s'"
                        % ports_msg)
        self._report_log.append(ports_msg)
      # TODO: Set a dummy port as the dependancy...
      return

    with self._lock:
      if depends in self._dependancies[typ]:
        ports_msg = (port, self._port.origin())
        if ports_msg not in self._report_log:
          self._log.warn("Multiple dependancies on port '%s' from port '%s'"
                         % ports_msg)
          self._report_log.append(ports_msg)
        return

      self._dependancies[typ].append(depends)
      depends.add_dependant(field, self, typ)

      status = depends.status()
      if status != DependHandler.RESOLV:
        self._count += 1
      if status == DependHandler.FAILURE:
        if self._status != DependHandler.FAILURE:
          self._status = DependHandler.FAILURE
          self._notify_all()

  def dependancies(self, typ=None):
    """
       Retrieve a list of dependancies, with all of them or just a subset

       @param typ: The subset of dependancies to get
       @type typ: C{int} or C{(int)}
       @return: A list of dependancies
       @rtype: C{(DependHandler)}
    """
    with self._lock:
      if typ is None:
        depends = self._dependancies
      elif isinstance(typ, int):
        depends = [self._dependancies[typ]]
      else:
        depends = []
        for i in typ:
          depends.append(self._dependancies[i])

      return tuple(set(sum(depends, [])))

  def add_dependant(self, field, depend, typ):
    """
       Add a dependant to our list

       @param field: The field data for the dependancy
       @type field: C{str}
       @param depend: The dependant
       @type depend: C{DependHandler}
       @param typ: The type of dependancy
       @type typ: C{int}
    """
    with self._lock:
      if self._status == DependHandler.RESOLV:
        if not self._update((field, depend), typ):
          self._status = DependHandler.UNRESOLV
          self._notify_all()

      self._dependants[typ].append((field, depend))

  def dependants(self, typ=None, fields=False):
    """
       Retrieve a list of dependant, with a subset of either a list of fields or
       of DependHandlers

       @param typ: The subset of dependancies to get
       @type typ: C{int} or C{(int)}
       @param fields: If the list should be a list of fields
       @type fields: C{bool}
       @return: The list of dependants fields or handlers
       @rtype: C{(DependHandler)} or C{(str)}
    """
    with self._lock:
      if typ is None:
        depends = self._dependants
      elif isinstance(typ, int):
        depends = [self._dependants[typ]]
      else:
        depends = []
        for i in typ:
          depends.append(self._dependants[typ])

      if fields:
        return tuple(set([i[0] for i in sum(depends, [])]))
      else:
        return tuple(set([i[1] for i in sum(depends, [])]))

  def check(self, stage):
    """
       Check the dependancy status for a given stage

       @param stage: The stage to check for
       @type stage: C{int}
       @return: The dependancy status
       @rtype: C{int}
    """
    # This should not be called if we have already failed
    assert self._status != DependHandler.FAILURE
    with self._lock:
      if self._count == 0 or stage == Port.CONFIG:
        return DependHandler.RESOLV
      return self._check(DependHandler.STAGE2DEPENDS[stage])

  def port(self):
    """
       Return the port this is a dependant handle for

       @return: The port
       @rtype: C{Port}
    """
    return self._port

  def update(self, depend):
    """
       Called when a dependancy has changes status

       @param depend: The dependancies dependant handler
       @type depend: C{DependHandler}
    """
    status = depend.status()
    with self._lock:
      if status == DependHandler.FAILURE:
        self._status = DependHandler.FAILURE
        delta = 0
      elif status == DependHandler.RESOLV:
        delta = 1
      else: # depend.status() == DependHandler.UNRESOLV
        delta = -1

      if delta:
        self._count += delta * \
                    len([i for i in sum(self._dependancies, []) if i == depend])
      if self._count < 0:
        self._log.error("Dependancy count with a negative number!!!")
        self._count = 0
      if not self._count:
        report = False
        for i in self.dependancies:
          if i.status() != DependHandler.RESOLV:
            report = True
            self._count += 1
        if report:
          self._log.error("Dependancy count wrong (%i)" % self._count)

  def status(self):
    """
       Returns the status of this port

       @return: The status
       @rtype: C{int}
    """
    with self._lock:
      return self._status

  def status_changed(self):
    """
       Indicates that our port's status has changed, this may mean either we
       now satisfy our dependants or not
    """
    if self._port.failed():
      status = DependHandler.FAILURE
      # TODO: We might have failed and yet still satisfy our dependants
    elif self._port.install_status() > Port.ABSENT:
      status = DependHandler.RESOLV
      if not self._verify():
        status = DependHandler.UNRESOLV
    else:
      status = DependHandler.UNRESOLV

    with self._lock:
      if status != self._status:
        self._status = status
        self._notify_all()

  def _check(self, depends):
    """
       Check if a list of dependancies has been resolved.

       @param depends: List of dependancies
       @type depends: C{int} or C{(int)}
    """
    if isinstance(depends, int):
      depends = [depends]

    for i in depends:
      for j in self._dependancies[i]:
        if j.status() != DependHandler.RESOLV:
          return DependHandler.UNRESOLV
    return DependHandler.PARTRESOLV

  def _notify_all(self):
    """
       Notify all dependants that we have changed status
    """
    for i in self._dependants:
      for j in i:
        j[1].update(self)

  def _update(self, data, typ):
    """
       Check if a dependancy has been resolved

       @param data: The field data and the dependant handler
       @type data: C{(str, DependHandler)}
       @param typ: The type of dependancy
       @type typ: C{int}
       @return: If the condition has been satisfied
       @rtype: C{bool}
    """
    field, depend = data
    if typ == DependHandler.BUILD:
      pass
    elif typ == DependHandler.EXTRACT:
      pass
    elif typ == DependHandler.FETCH:
      pass
    elif typ == DependHandler.LIB:
      pass
    elif typ == DependHandler.RUN:
      pass
    elif typ == DependHandler.PATCH:
      pass

    if self._port.install_status() == Port.ABSENT:
      return False
    else:
      return True

  def _verify(self):
    """
       Check that we actually satisfy all dependants
    """
    for i in range(DependHandler.PATCH):
      for j in self._dependants[i]:
        if not self._update(j, i):
          return False
    return True

class PortCache(dict):
  """
     The PortCache class.  This class keeps a cache of Port objects
     (note: this is an inflight cache)
  """
  from logging import getLogger

  _log = getLogger('pypkg.cache')  #: Logger for this cache

  def __init__(self):
    """
       Initialise the cache of ports
    """
    dict.__init__(self)

    from threading import Condition, Lock

    self._lock = Condition(Lock())  #: The lock for this cache
    self.__dead_cnt = 0  #: The number of 'bad' ports

  def __len__(self):
    """
       The number of ports loaded.

       @return: Number of ports
       @rtype: C{int}
    """
    return dict.__len__(self) - self.__dead_cnt

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
    key = self._normalise(key)
    with self._lock:
      try:
        value = dict.__getitem__(self, key)
        if value:
          return value
      except KeyError:
        self.add(key)
      else:
        if value is False:
          raise KeyError, key

      while True:
        if dict.has_key(self, key) and dict.__getitem__(self, key) != None:
          value = dict.__getitem__(self, key)
          if value:
            return value
          else:
            raise KeyError, key
        self._lock.wait()

  def __setitem__(self, key, value):
    """
       Records a port in the cache

       @param key: The ports name
       @type key: C{str}
       @param value: The port object
       @type value: C{str}
    """
    key = self._normalise(key)
    with self._lock:
      dict.__setitem__(self, key, value)

  def has_key(self, k):
    """
       Check if a port exists

       @param k: The ports origin
       @type k: C{str}
       @return: If the port exists
       @rtype: C{bool}
    """
    k = self._normalise(k)
    try:
      PortCache.__getitem__(self, k)
      return True
    except KeyError:
      return False

  def add(self, key):
    """
       Adds a port to be contructed if not already in the cache or queued for
       construction

       @param key: The port for queueing
       @type key: C{str}
       @return: The job ID of the queued port
       @rtype: C{int}
    """
    key = self._normalise(key)
    from queue import ports_queue
    if not dict.has_key(self, key):
      return ports_queue.put_nowait(lambda: self._get(key))

  def get(self, k, d=None):
    """
       Get a port from the database.

       @param k: The ports origin
       @type k: C{str}
       @param d: The default argument
       @return: The port or None
       @rtype: C{Port}
    """
    try:
      return self[k]
    except KeyError:
      return d

  def _get(self, key):
    """
       Create a port and add it to the database

       @param key: The port to get
       @type key: C{str}
    """
    from os.path import isdir, join
    with self._lock:
      try:
        dict.__getitem__(self, key)
        return
      except KeyError:
        dict.__setitem__(self, key, None)

    try:
      # Time consuming task, done outside lock
      if isdir(join(env['PORTSDIR'], key)) and len(key.split('/')) == 2:
        port = Port(key)
      else:
        port = False
        self._log.error("Invalid port name '%s' passed" % key)
      self._lock.acquire()
    except KeyboardInterrupt:
      raise
    except BaseException:
      self._lock.acquire()
      port = False
      self._log.exception("Error while creating port '%s'" % key)
    dict.__setitem__(self, key, port)
    if not port:
      self.__dead_cnt += 1
    self._lock.notifyAll()
    self._lock.release()

  def _normalise(self, origin):
    """
       Normalise the name of a port

       @param origin: The current name of the port
       @type origin: C{str}
       @return: The normalised name of the port
       @rtype: C{str}
    """
    from os import sep
    new = origin.strip().rstrip('/').split('/')
    index = 0
    while index < len(new):
      if new[index] in ('.', ''):
        new.pop(index)
      elif new[index] == '..':
        if index == 0:
          self._log.warn("Port name escapes port directory: '%s'" % origin)
          return origin
        new.pop(index)
        new.pop(index - 1)
        index -= 1
      else:
        index += 1

    new = sep.join(new)
    if new != origin:
      self._log.warn("Non standard port name used: '%s'" % origin)
    return new
    

port_cache = PortCache()

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
  pkg_version = Popen(['pkg_version', '-O', origin], close_fds=True,
                      stdout=PIPE, stderr=STDOUT)
  if pkg_version.wait() != 0:
    return Port.ABSENT

  info = pkg_version.stdout.read().split()
  if len(info) > 2:
    from logging import getLogger
    getLogger('pypkg.port_status').warning("Multiple ports with same origin " \
                                           "'%s'" % origin)
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
  from make import make_target, SUCCESS

  if env['PORTSDIR'][-1] != '/':
    env['PORTSDIR'].join('/')

  args = []
  for i in ports_attr.itervalues():
    args.append('-V')
    args.append(i[0])

  make = make_target(origin, args, pipe=True)
  if make.wait() is not SUCCESS:
    raise RuntimeError, "Error in obtaining information for port '%s'" % origin

  attr_map = {}
  for name, value in ports_attr.iteritems():
    if value[1] is str:
      attr_map[name] = make.stdout.readline().strip()
    else:
      attr_map[name] = value[1](make.stdout.readline().split())
    for i in value[2:]:
      attr_map[name] = i(attr_map[name])

  return attr_map
