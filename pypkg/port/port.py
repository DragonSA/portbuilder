"""
The Port module.  This module contains all classes and utilities needed for
managing port information.  
"""
from __future__ import absolute_import, with_statement

__all__ = ['Port']

def check_config(optionfile, pkgname):
  """
     Check the options file to see if it is upto date, if so return False

     @param optionfile: The file containing the options
     @type optionfile: C{str}
     @param pkgname: The full versioned name of the port
     @type pkgname: C{str}
     @return: If the port needs to be configured
     @rtype: C{bool}
  """
  from os.path import isfile

  if isfile(optionfile):
    for i in open(pkgname, 'r'):
      if i.startswith('_OPTIONS_READ='):
        if i[14:-1] == pkgname:
          return False
        else:
          return True
  return True

def get_www(descr):
  """
      Get the WWW address in the description file

      @param descr: The description file
      @type descr: C{str}
      @return: The WWW URL
      @rtype: C{str}
  """
  from os.path import isfile

  if isfile(descr):
    for i in open(descr, 'r'):
      i = i.strip()
      if i.startswith('WWW:'):
        www = i[4:].lstrip()
        if www.split('://', 1)[0] in ('http', 'https', 'ftp'):
          return www
        return 'http://' + www
  else:
    # TODO
    #self._log.warn("Invalid description file for '%s'" % self._origin)
    pass
  return ''

def recurse_depends(port, category, cache=dict()):
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
    from pypkg.port import cache as pcache
    depends = set()
    for i in set([j[1] for j in sum([port.attr(i) for i in categories], [])]):
      i_p = pcache.get(i)
      if i_p:
        depends.add(i_p.attr('pkgname'))
        depends.update(cache.has_key(i) and cache[i] or retrieve(i_p, master))
      else:
        # TODO
        #self._log.warn("Port '%s' has a (indirect) stale dependancy " \
                      #"on '%s'" % (port.origin(), i))
        pass

    depends = list(depends)
    depends.sort()

    if set(category) == set(master):
      cache[port.origin()] = tuple(depends)

    return depends

  if set(category) == set(master) and cache.has_key(port.origin()):
    return " ".join(cache[port.origin()])
  return " ".join(retrieve(port, category))


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

  force_noconf = False  #: If the port should not configure itself
  force_config = False  #: Force issueing a `make config'
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
    from pypkg.port import cache
    from pypkg.port.arch import attr, status
    self._origin = origin  #: The origin of the port
    self._install_status = status(origin) #: The install status of the port
    self._stage = 0  #: The (build) stage progress of the port
    self._attr_map = {}  #: The ports attributes
    self._working = False  #: Working flag
    self._failed = False  #: Failed flag
    self._depends = None  #: The dependant handlers for various stages

    self._attr_map = attr(origin)

    for i in self._attr_map['depends']:
      cache.add(i)

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

    from pypkg.port import DependHandler

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

    from pypkg.make import env

    build_depends = ('depend_build', 'depend_lib')
    extract_depends = ('depend_extract',)
    fetch_depends = ('depend_fetch',)
    patch_depends = ('depend_patch',)
    run_depends = ('depend_lib', 'depend_run')

    return "|".join((
           self.attr('pkgname'),                   # ${PKGNAME}
           join(env['PORTSDIR'], self._origin),    # ${PORTDIR}/${ORIGIN}
           self.attr('prefix'),                    # ${PREFIX}
           self.attr('comment'),                   # ${COMMENT}
           self.attr('descr'),                     # ${DESCR_FILE}
           self.attr('maintainer'),                # ${MAINTAINER}
           " ".join(self.attr('category')),        # ${CATEGORIES}
           recurse_depends(self, build_depends),   # ${BUILD_DEPENDS}
           recurse_depends(self, run_depends),     # ${RUN_DEPENDS}
           get_www(self.attr('descr')),            # ${WWW_SITE}
           recurse_depends(self, extract_depends), # ${EXTRACT_DEPENDS}
           recurse_depends(self, patch_depends),   # ${PATCH_DEPENDS}
           recurse_depends(self, fetch_depends),   # ${FETCH_DEPENDS}
           )) 

  def clean(self):
    """
       Clean the ports working directories.

       @return: The clean status
       @rtype: C{bool}
    """
    from pypkg.make import clean_log, make_target, SUCCESS

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
    from pypkg.target import config_builder, fetch_builder, build_builder, \
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
    from pypkg.port import cache
    from pypkg.make import make_target, SUCCESS

    if len(self._attr_map['options']) == 0 or Port.force_noconfig:
      return True
    elif Port.force_config or check_config(self.attr('optionsfile'),
                                           self.attr('pkgname')):
      make = make_target(self._origin, 'config', pipe=False)
      status = make.wait() is SUCCESS

      if status:
        from pypkg.port.arch import attr
        self._attr_map = attr(self._origin)
        for i in self._attr_map['depends']:
          cache.add(i)

      return status

  fetch = lambda self: self.build_stage(Port.FETCH)
  def _fetch(self):
    """
       Fetches the distribution files for this port

       @return: The success status
       @rtype: C{bool}
    """
    from pypkg.make import make_target, SUCCESS

    return make_target(self._origin, ['checksum']).wait() is SUCCESS

  build = lambda self: self.build_stage(Port.BUILD)
  def _build(self):
    """
        Build the port.  This includes extracting, patching, configuring and
        lastly building the port.

        @return: The success status
        @rtype: C{bool}
    """
    from pypkg.make import make_target, SUCCESS

    #make = make_target(self._origin, ['clean', 'extract', 'patch', 'configure',
                                      #'build'])
    return make_target(self._origin, ['clean', 'all']).wait() is SUCCESS

  install = lambda self: self.build_stage(Port.INSTALL)
  def _install(self):
    """
        Install the port.

        @return: The success status
        @rtype: C{bool}
    """
    from pypkg.make import make_target, SUCCESS

    make = make_target(self._origin, ['install'] +
                       (Port.package and ['package'] or []))

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
    from pypkg.port import DependHandler
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
      if status in (DependHandler.FAILURE, DependHandler.UNRESOLV):
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
