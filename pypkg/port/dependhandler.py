"""
The Depend Handler module.  This module contains the depend handling code for
Port
"""
from __future__ import absolute_import, with_statement

from pypkg.port import Port

__all__ = ['DependHandler']

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
    from pypkg.port import cache
    try:
      depends = cache[port].depends()
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
    # DependHandler status might change without Port's changing
    with self._lock:
      if self._status == DependHandler.FAILURE:
        return self._status
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
