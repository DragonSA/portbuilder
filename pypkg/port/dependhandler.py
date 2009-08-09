"""
The Depend Handler module.  This module contains the depend handling code for
Port
"""
from __future__ import absolute_import, with_statement

from .port import Port

__all__ = ['Dependant', 'Dependancy']

class DependHandler(object):
  """
     The DependHandler class.  This class provides common declarations to both
     Dependant and Dependancy.
  """
  from logging import getLogger
  from ..threads import WatchRLock as RLock

  # The type of dependancies
  BUILD   = 0  #: Build dependants
  EXTRACT = 1  #: Extract dependants
  FETCH   = 2  #: Fetch dependants
  LIB     = 3  #: Library dependants
  RUN     = 4  #: Run dependants
  PATCH   = 5  #: Patch dependants

  STAGE2DEPENDS = {
    Port.CONFIG:  (),                           # The config dependancies
    Port.FETCH:   (FETCH,),                     # The fetch dependancies
    Port.BUILD:   (EXTRACT, PATCH, LIB, BUILD), # The build dependancies
    Port.INSTALL: (LIB, RUN),                   # The install dependancies
  } #: The dependancies for a given stage

  _lock = RLock()
  _log = getLogger("pypkg.depend_handler")

class Dependant(DependHandler):
  """
     The Dependant class.  This class tracks the dependants for a Port.
  """

  # The dependant status
  FAILURE  = -1  #: The port failed and/or cannot resolve dependants
  UNRESOLV = 0   #: Port does not satisfy dependants
  RESOLV   = 1   #: Dependants resolved

  from logging import getLogger
  from ..threads import WatchRLock as RLock

  _log = getLogger("pypkg.dependant")

  def __init__(self, port, depends=None):
    """
       Initialise the databases of dependants

       @param port: The port this is a dependant handler for
       @type port: Port
    """
    self._dependants   = [[], [], [], [], [], []]  #: All dependants
    self._port = port  #: The port whom we handle
    self._report_log = []  #: Log of all problems reported (to prevent dups)
    # TODO: Change to actually check if we are resolved
    # Port._install depends on install_status having been called here
    if port.install_status() > Port.ABSENT:
      self._status = Dependant.RESOLV
    else:
      self._status = Dependant.UNRESOLV

  def add(self, field, port, typ):
    """
       Add a dependant to our list

       @param field: The field data for the dependant
       @type field: C{str}
       @param depend: The port
       @type depend: C{Port}
       @param typ: The type of dependant
       @type typ: C{int}
    """
    with self._lock:
      if self._status == Dependant.RESOLV:
        if not self._update(field, typ):
          self._status = Dependant.UNRESOLV
          self._notify_all()

      self._dependants[typ].append((field, port))

  def get(self, typ=None):
    """
       Retrieve a list of dependants.

       @param typ: The subset of dependancies to get
       @type typ: C{int} or C{(int)}
       @return: The list of dependants fields or handlers
       @rtype: C{(Port)}
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

    return tuple(set([i[1] for i in sum(depends, [])]))

  def update(self, depend):
    """
       Called when a dependancy has changes status

       @param depend: The dependancies dependant handler
       @type depend: C{DependHandler}
    """
    status = depend.status()
    with self._lock:
      if self._status == Dependant.FAILURE:
        # We have failed, no need to continue
        return

      if status == Dependant.FAILURE:
        if self._status == Dependant.UNRESOLV:
          # We will never satisfy our dependants
          self._status = Dependant.FAILURE
          self._notify_all()

  def port(self):
    """
       Return the port this is a dependant handle for

       @return: The port
       @rtype: C{Port}
    """
    return self._port

  def status(self):
    """
       Returns the status of this port.

       @return: The status
       @rtype: C{int}
    """
    return self._status

  def failed(self):
    """
       Shorthand for self.status() == Dependant.FAILURE

       @return: The failed status
       @rtype: C{bool}
    """
    return self._status == Dependant.FAILURE

  def status_changed(self):
    """
       Indicates that our port's status has changed, this may mean either we
       now satisfy our dependants or not.
    """
    if self._port.failed():
      status = Dependant.FAILURE
      # TODO: We might have failed and yet still satisfy our dependants
    elif self._port.install_status() > Port.ABSENT:
      status = Dependant.RESOLV
      if not self._verify():
        # TODO: We may satisfy some dependants, but not others,
        # If we still do not satisfy our dependants then haven't we failed?
        status = Dependant.FAILURE
    else:
      status = Dependant.UNRESOLV

    with self._lock:
      if status != self._status:
        self._log.debug("Status changed from %i to %i for port: ``%s''" %
                                   (self._status, status, self._port.origin()))
        self._status = status
        self._notify_all()

  def _notify_all(self):
    """
       Notify all dependants that we have changed status.
    """
    for i in self.get():
      i.dependant().update(self)
      i.dependancy().update(self)

  def _update(self, field, typ):
    """
       Check if a dependant has been resolved.

       @param data: The field data
       @type data: C{str}
       @param typ: The type of dependant
       @type typ: C{int}
       @return: If the condition has been satisfied
       @rtype: C{bool}
    """
    field
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

    return self._port.install_status() != Port.ABSENT

  def _verify(self):
    """
       Check that we actually satisfy all dependants.
    """
    for i in range(len(self._dependants)):
      for j in self._dependants[i]:
        if not self._update(j[0], i):
          return False
    return True


class Dependancy(DependHandler):
  """
     The Dependancy class.  This class tracking the dependanies of a Port
  """

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
    self._port = port  #: The port whom we handle
    self._report_log = []  #: Log of all problems reported (to prevent dups)

    if not depends:
      depends = [[]]
    elif len(depends) != len(self._dependancies):
      self._log.warn("Incomplete list of dependancies passed")

    for i in range(len(depends)):
      for j in depends[i]:
        self.__add(j[0], j[1], i)

  def __add(self, field, port, typ):
    """
       Add a dependancy to our list

       @param field: The field data for the dependancy
       @type field: C{str}
       @param port: The dependant
       @type port: C{str}
       @param typ: The type of dependancy
       @type typ: C{int}
    """
    from ..port import cache
    try:
      port = cache[port]
    except KeyError:
      ports_msg = (self._port.origin(), port)
      if ports_msg not in self._report_log:
        self._log.error("Port '%s' has a stale dependancy on port '%s'"
                        % ports_msg)
        self._report_log.append(ports_msg)
      # TODO: Set a dummy port as the dependancy...
      return

    with self._lock:
      if port in self._dependancies[typ]:
        ports_msg = (port.origin(), self._port.origin())
        if ports_msg not in self._report_log:
          self._log.warn("Multiple dependancies on port '%s' from port '%s'"
                         % ports_msg)
          self._report_log.append(ports_msg)
        return

      self._dependancies[typ].append(port)
      port.dependant().add(field, self._port, typ)

      status = port.dependant().status()
      if status != Dependant.RESOLV:
        self._count += 1
      if status == Dependant.FAILURE:
        if self._status != Dependant.FAILURE:
          self._status = Dependant.FAILURE
          self._notify_all()

  def get(self, typ=None):
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

  def check(self, stage):
    """
       Check the dependancy status for a given stage

       @param stage: The stage to check for
       @type stage: C{int}
       @return: The dependancy status
       @rtype: C{bool}
    """
    # DependHandler status might change without Port's changing
    with self._lock:
      if self._count == 0 or not sum([len(self._dependancies[i]) for i in
          Dependancy.STAGE2DEPENDS[stage]]):
        return True
      else:
        for i in Dependancy.STAGE2DEPENDS[stage]:
          for j in self._dependancies[i]:
            if j.dependant().status() != Dependant.RESOLV:
              return False
        return True

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
      if status == Dependant.FAILURE:
        delta = -1
      elif status == Dependant.RESOLV:
        delta = 1
      else: # depend.status() == DependHandler.UNRESOLV
        delta = -1

      self._count -= delta * \
                    len([i for i in sum(self._dependancies, []) if i == depend])
      if self._count < 0:
        self._log.error("Dependancy count with a negative number!!!")
        self._count = 0
      if not self._count:
        # Check that we do actually have all the dependancies met
        # TODO: Remove, debug check
        report = False
        for i in self.get():
          if i.status() != Dependant.RESOLV:
            report = True
            self._count += 1
        if report:
          self._log.error("Dependancy count wrong (%i)" % self._count)
