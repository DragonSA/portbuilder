"""
The Port module.  This module contains all classes and utilities needed for
managing port information.
"""
from __future__ import absolute_import, with_statement

from contextlib import contextmanager

__all__ = ['Port']

def check_config(optionfile, pkgname):
  """
     Check the options file to see if it is up-to-date, if so return False.

     @param optionfile: The file containing the options
     @type optionfile: C{str}
     @param pkgname: The full versioned name of the port
     @type pkgname: C{str}
     @return: If the port needs to be configured
     @rtype: C{bool}
  """
  from logging import getLogger

  from os.path import isfile

  if isfile(optionfile):
    for i in open(optionfile, 'r'):
      if i.startswith('_OPTIONS_READ='):
        # The option set to the last pkgname this config file was set for
        if i[14:-1] == pkgname:
          return False
        else:
          return True
    getLogger('pypkg.port').warn("Options file is corrupt: %s" % optionfile)
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
  from logging import getLogger

  if isfile(descr):
    for i in open(descr, 'r'):
      i = i.strip()
      if i.upper().startswith('WWW:'):
        www = i[4:].lstrip()
        if www.split('://', 1)[0] in ('http', 'https', 'ftp'):
          return www
        else:
          return 'http://' + www
    getLogger('pypkg.port').warn("Description file does not provide a WWW" \
                                                       "address: %s" % descr)
  else:
    getLogger('pypkg.port').warn("Invalid description file for '%s'" % descr)
  return ''

def recurse_depends(port, category, cache=dict()):
  """
    Returns a sorted list of dependancies pkgname.  Only the categories are
    evaluated.

    @param port: The port the dependancies are for
    @type port: C{Port}
    @param category: The dependancies to retrieve
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

      @param port: The port the dependancies are for
      @type port: C{Port}
      @param category: The dependancies to retrieve
      @type category: C{(str)}
      @return: The sorted list of dependancies
      @rtype: C{(str)}
    """
    from logging import getLogger

    from pypkg.port import cache as pcache

    depends = set()
    # Iterate over all dependancies in the given categories
    for i in set([j[1] for j in sum([port.attr(i) for i in categories], [])]):
      i_p = pcache.get(i)
      if i_p:
        # Add the dependancy to our list
        depends.add(i_p.attr('pkgname'))
        # Add all its dependancies to our list (either via cache or direct)
        depends.update(cache.has_key(i) and cache[i] or retrieve(i_p, master))
      else:
        getLogger('pypkg.port').warn("Port %s has a stale dependancy: %s" %
                                                            (port.origin(), i))

    depends = list(depends)
    depends.sort()

    # Cache the dependancies if they are the master (otherwise cache will not
    # be used)
    if set(category) == set(master):
      cache[port.origin()] = tuple(depends)

    return depends

  if set(category) == set(master) and cache.has_key(port.origin()):
    return " ".join(cache[port.origin()])
  return " ".join(retrieve(port, category))

class FetchLock(object):
  """
     A fetch lock, excludes fetching the same files from different ports.
  """
  def __init__(self):
    """
       Initialise the locks and database of files.
    """
    from threading import Condition, Lock

    self.__lock = Condition(Lock())
    self._files = []

  def acquire(self, files, blocking=True):
    """
       Acquire a lock for the given files.

       @param files: The files to lock on
       @type files: C{[str]}
       @param blocking: If we should wait to lock
       @type blocking: C{bool}
       @return: If the lock was acquired
       @rtype: C{bool}
    """
    with self.__lock:
      while True:
        wait = False
        # Check if the files are already locked
        for i in files:
          if i in self._files:
            wait = True
            break
        if wait:
          # Some of the files are locked, either wait or bail
          if not blocking:
            return False
          else:
            self.__lock.wait()
        else:
          # Files are not locked, lock them
          self._files += files
          return True

  def release(self, files):
    """
       Release a lock fir the given files.

       @param files: The files locked on
       @type files: C{[str]}
    """
    for i in files:
      assert i in self._files

    with self.__lock:
      # Remove the files from being locked
      for i in files:
        self._files.remove(i)
      self.__lock.notify()

  @contextmanager
  def lock(self, files):
    """
       Create a context manager for a lock of the given files.

       @param files: The files to lock on
       @type files: C{[str]}
    """
    self.acquire(files)
    try:
      yield
    finally:
      self.release(files)

class Port(object):
  """
     The class that contains all information about a given port, such as status,
     dependancies and dependants.
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

  force_noconfig = False  #: If the port should not configure itself
  force_config = False  #: Force issueing a `make config'
  fetch_only = False  #: Only fetch the port, skip all other stages
  package = False  #: If newly installed ports should be packaged

  _log = getLogger("pypkg.port")
  __lock = Condition(Lock())  #: The notifier and locker for all ports
  __lock_fetch = FetchLock()  #: Mutual exclusion lock for fetching file

  def __init__(self, origin):
    """
       Initialise the port and all its information.

       @param origin: The ports origin (within the ports tree)
       @type origin: C{str}
    """
    from pypkg.port import cache
    from pypkg.port.arch import attr, status

    self._attr_map = attr(origin)  #: The ports attributes
    self._depends = None  #: The dependant handlers for various stages
    self._install_status = status(origin, self._attr_map) #: The install status
    self._origin = origin  #: The origin of the port

    self.__failed = False  #: Failed flag
    self.__stage = 0  #: The (build) stage progress of the port
    self.__working = False  #: Working flag

    for i in self._attr_map['depends']:
      cache.add(i)

  def attr(self, attr):
    """
       Returns the ports attributes, such as version, categories, etc.

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
    return self.__failed

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
    return self.__lock

  def log_file(self):
    """
       The log file of this port. (See also make.

       @return: The path to the log file
       @rtype: C{str}
    """
    from os.path import join

    from pypkg.env import dirs

    return join(dirs['log_port'], self._origin.replace('/', '_'))

  def stage(self):
    """
       The currently (building or completed) stage.

       @return: The build status
       @rtype: C{int}
    """
    return self.__stage

  def origin(self):
    """
       The origin of this port.

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
    return self.__working

  def depends(self):
    """
       Returns the dependant handler for this port.

       WARNING: Dead lock will occure if there is a cyclic port dependancy.

       @return: The dependant handler
       @rtype: C{DependHandler}
    """
    if self._depends:
      return self._depends

    from pypkg.port import DependHandler

    with self.__lock:
      # Wait for another request of the depend handler is pending
      while self._depends is False:
        self.__lock.wait()

      # If depend handler has not been created
      if not self._depends:
        if not self.__failed:
          # Reserve the depend handler, still creating it
          self._depends = False
        else:
          # Port already failed, create empty depend handler
          self._depends = DependHandler(self)

    # If the depend handler was created by another thread
    if self._depends:
      return self._depends

    # We need to be configured before the depend handler can be created
    if self.__stage < Port.CONFIG:
      self.config()

    # Create the depend handler (for all our dependancies)
    self._log.debug("Creating depend handler: %s" % self._origin)
    depends_obj = DependHandler(self, [self.attr(i) for i in
                  ('depend_build', 'depend_extract', 'depend_fetch',
                   'depend_lib',   'depend_run',     'depend_patch')])

    with self.__lock:
      # Set the depend handler and notify any other threads
      self._depends = depends_obj
      self.__lock.notifyAll()

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
    from pypkg.make import make_target, SUCCESS

    assert not self.__working

    self._log.debug("Cleaning: %s" % self._origin)

    # Clean the port itself
    status = make_target(self._origin, ['clean']).wait() is SUCCESS

    if not self.__failed:
      from os.path import isfile
      from os import unlink

      # If we have not failed then remove the log file
      log_file = self.log_file()
      if isfile(log_file):
        unlink(log_file)

    with self.__lock:
      # If we had completed building and run a clean then (obviously) we are
      # back to a FETCH stage
      if not self.__failed and self.__stage is Port.BUILD:
        self.__stage = Port.FETCH
        self.__working = False

    return status

  def build_stage(self, stage, queue=True):
    """
       Generic handler for building a stage, this calls the correct method.
       This does not add the port to the construction queue and should only
       be called by the correstonding _builder (Note: private but friendly C++).

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
      # Some effieciency checks.
      with self.__lock:
        if self.__failed:
          return False
        elif self.__stage > stage:
          return True

      # Place the port to be build by the proper stage builder
      stage_builder[stage](self)

      # Wait for the stage to be completed
      with self.__lock:
        while (self.__stage < stage or (self.__working and \
               self.__stage == stage)) and not self.__failed:
          self.__lock.wait()

        return not self.__failed
    else:
      proceed, status = self.__prepare(stage)
      if not proceed:
        return status

      # Actually do the stage
      status = stage_handler[stage]()

      return self.__finalise(stage, status)

  config = lambda self: self.build_stage(Port.CONFIG)
  def _config(self):
    """
       Configure the ports options.

       @return: The success status
       @rtype: C{bool}
    """
    from pypkg.port import cache
    from pypkg.make import Make, make_target, SUCCESS

    # If the port has options and they are out of date or configuring is
    # requested then configure the port
    if len(self._attr_map['options']) != 0  and not Port.force_noconfig and \
         check_config(self.attr('optionsfile'), self.attr('pkgname')) or \
         Port.force_config:
      make = make_target(self._origin, 'config', pipe=False, priv=True)
      status = make.wait() is SUCCESS

      # If we actually configured the port then refetch the ports attr
      if status and not Make.no_opt:
        from pypkg.port.arch import attr

        self._attr_map = attr(self._origin)
        for i in self._attr_map['depends']:
          cache.add(i)

      return status
    else:
      return True

  fetch = lambda self: self.build_stage(Port.FETCH)
  def _fetch(self):
    """
       Fetches the distribution files for this port

       @return: The success status
       @rtype: C{bool}
    """
    from os.path import join

    from pypkg.cache import check_files, set_files
    from pypkg.env import iscreatable
    from pypkg.make import Make, make_target, SUCCESS

    distdir = self.attr('distdir')
    distfiles = [(i, join(distdir, i)) for i in self.attr('distfiles')]

    with self.__lock_fetch.lock(self.attr('distfiles')):
      status = True
      for i in distfiles:
        # Check if the files exist and/or have changed
        files = check_files('distfiles', i[0])
        if not files or files[0] != i[1]:
          status = False
          break

      # Files have not changed since last being fetched
      if status:
        return True

      priv = False
      for i in distfiles:
        # If the files can be created then no need for privilage
        if not iscreatable(i[1]):
          priv = True
          break

      make = make_target(self._origin, ['checksum'], priv=priv)
      status = make.wait() is SUCCESS

      if status and not Make.no_opt:
        for i in distfiles:
          # Record the files (to prevent future fetching)
          set_files('distfiles', i[0], i[1])
      return status

  build = lambda self: self.build_stage(Port.BUILD)
  def _build(self):
    """
        Build the port.  This includes extracting, patching, configuring and
        lastly building the port.

        @return: The success status
        @rtype: C{bool}
    """
    from pypkg.env import iscreatable
    from pypkg.make import mkdir, make_target, SUCCESS

    #make = make_target(self._origin, ['clean', 'extract', 'patch', 'configure',
                                      #'build'])

    # Try to create the workdir so that it is writable by this process
    if not iscreatable(self.attr('wrkdir')):
      priv = not mkdir(self.attr('wrkdir'))
    else:
      priv = False

    # If this port is interactive allow it to take over the console
    pipe = self.attr('interactive') and False or None

    make = make_target(self._origin, ['clean', 'all'], pipe, priv)

    return make.wait() is SUCCESS

  install = lambda self: self.build_stage(Port.INSTALL)
  def _install(self):
    """
        Install the port.

        @return: The success status
        @rtype: C{bool}
    """
    from pypkg.make import Make, make_target, SUCCESS

    if self.install_status() == Port.ABSENT:
      args = ['install']
    else:
      # Port already exists and needs to be reinstalled
      args = ['deinstall', 'reinstall']
    if Port.package:
      # Package the port (regardless of restrictions)
      args += ['package']
      if self.attr('no_package'):
        args += '-DFORCE_PACKAGE'
        self._log.warn("Forcing package build for ``%s''" % self._origin)

    make = make_target(self._origin, args, priv=True)

    status = Port.INSTALL, make.wait() is SUCCESS
    if status:
      from os.path import isfile, join

      from pypkg.port.arch import status
      from pypkg.make import env
 
      #  Don't need to lock to change this as it will already have been set
      pkg_message = join(env['PORTSDIR'], self._origin, 'pkg-message')
      if isfile(pkg_message):
        # Port has a message, record it
        self._log.info("Port '%s' has the following message:\n%s" %
                       (self._origin, open(pkg_message).read()))

      # Update the install status (and notify depend handler of our change)
      install_status = self._install_status
      self._install_status = Make.no_opt and Port.CURRENT or \
                              status(self._origin, self._attr_map)
      if install_status != self._install_status:
        self._depends.status_changed()

    return status

  def __prepare(self, stage):
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

    # Make sure we have a depend handler
    if stage > Port.CONFIG:
      self.depends()

    with self.__lock:
      # This port is busy with a stage, wait for it to complete
      while self.__working:
        self.__lock.wait()

      # The port has fail
      if self.__failed and stage >= self.__stage:
        return False, False

      # This stage has already completed
      if stage <= self.__stage:
        return False, True

      # We are only fetching, fail for any other stage
      # TODO: Remove, should be handled in target_builder
      if Port.fetch_only and stage > Port.FETCH:
        self.__stage = stage
        self.__failed = True
        self._depends.status_changed()
        self.__lock.notifyAll()
        return False, False

      assert self.__stage == stage - 1

      self.__stage = stage

      status = stage > Port.CONFIG and self.depends().check(stage) or True

      # If the dependancies have failed then abort
      if not status:
        self._log.error("Failed to build stage %s due to dependancy failure: "\
                        "%s" % (Port.STAGE_NAME[stage], self._origin))
        self.__failed = True
        self._depends.status_changed()
        self.__lock.notifyAll()
        return False, False

      self.__working = time()

      self._log.debug("Starting stage %s: %s" % (Port.STAGE_NAME[stage],
                                                                 self._origin))

      return True, True

  def __finalise(self, stage, status):
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
    assert self.__working and not self.__failed

    with self.__lock:
      self.__working = False

      # If we have failed notify our depend handler
      if not status:
        assert not self.__failed

        self.__failed = True
        self._depends.status_changed()
      self.__lock.notifyAll()

    # Clean up after ourselves
    if not status and stage > Port.FETCH or stage is Port.INSTALL:
      self.clean()

    if self.__failed:
      self._log.error("Port has failed to complete stage %s: %s"
                      % (Port.STAGE_NAME[stage], self._origin))
    else:
      self._log.debug("Finished stage %s: %s" % (Port.STAGE_NAME[stage],
                                                                 self._origin))

    return status
