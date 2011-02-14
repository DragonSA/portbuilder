"""Dependancy handling for ports."""
from .port import Port

__all__ = ['Dependant', 'Dependancy']

class DependHandler(object):
  """Common declarations to both Dependant and Dependancy."""

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
    Port.PKGINSTALL: (LIB, RUN),                # The pkginstall dependencies
  } #: The dependancies for a given stage

class Dependant(DependHandler):
  """Tracks the dependants for a Port."""

  # The dependant status
  FAILURE  = -1  #: The port failed and/or cannot resolve dependants
  UNRESOLV = 0   #: Port does not satisfy dependants
  RESOLV   = 1   #: Dependants resolved

  def __init__(self, port):
    """Initialise the databases of dependants."""
    DependHandler.__init__(self)
    self._dependants   = [[], [], [], [], [], []]  #: All dependants
    self.port = port  #: The port whom we handle
    # TODO: Change to actually check if we are resolved
    # Port._install depends on install_status having been called here
    if port.install_status > Port.ABSENT:
      self.status = Dependant.RESOLV
    else:
      self.status = Dependant.UNRESOLV
    self.port.stage_completed.connect(self.status_changed)

  def add(self, field, port, typ):
    """Add a dependant to our list."""
    if self.status == Dependant.RESOLV:
      if not self._update(field, typ):
        self.status = Dependant.UNRESOLV
        self._notify_all()

    self._dependants[typ].append((field, port))

  def get(self, typ=None):
    """Retrieve a list of dependants."""
    if typ is None:
      depends = self._dependants
    elif isinstance(typ, int):
      depends = [self._dependants[typ]]
    else:
      depends = []
      for i in typ:
        depends.append(self._dependants[i])

    return tuple(set([i[1] for i in sum(depends, [])]))

  @property
  def failed(self):
    """Shorthand for self.status() == Dependant.FAILURE."""
    return self.status == Dependant.FAILURE

  def status_changed(self, stage=None):
    """Indicates that our port's status has changed."""
    if stage is not None and (not self.port.failed or stage < Port.INSTALL):
      return
    if self.port.failed or (self.port.dependancy and self.port.dependancy.failed):
      status = Dependant.FAILURE
      # TODO: We might have failed and yet still satisfy our dependants
    elif self.port.install_status > Port.ABSENT:
      status = Dependant.RESOLV
      if not self._verify():
        # TODO: We may satisfy some dependants, but not others,
        # If we still do not satisfy our dependants then haven't we failed?
        status = Dependant.FAILURE
    else:
      status = Dependant.UNRESOLV

    if status != self.status:
      self.status = status
      self._notify_all()

  def _notify_all(self):
    """Notify all dependants that we have changed status."""
    for i in self.get():
      i.dependancy.update(self)

  def _update(self, _field, typ):
    """Check if a dependant has been resolved."""
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

    return self.port.install_status != Port.ABSENT

  def _verify(self):
    """Check that we actually satisfy all dependants."""
    for i in range(len(self._dependants)):
      for j in self._dependants[i]:
        if not self._update(j[0], i):
          return False
    return True

class Dependancy(DependHandler):
  """Tracks the dependanies for a Port."""

  def __init__(self, port, depends=None):
    """Initialise the databases of dependancies."""
    from . import get_port

    DependHandler.__init__(self)
    self._count = 0  #: The count of outstanding dependancies
    self._dependancies = [[], [], [], [], [], []]  #: All dependancies
    self._loading = 0
    self.failed = False  #: If a dependancy has failed
    self.port = port  #: The port whom we handle

    if not depends:
      depends = [[]]

    for i in range(len(depends)):
      for j in depends[i]:
        self._loading += 1
        get_port(j[1], lambda x: self._add(x, j[0], i))

  def _add(self, port, field, typ):
    """Add a port to our dependancy list."""
    self._loading -= 1

    if port is not None:
      if port not in self._dependancies[typ]:
        self._dependancies[typ].append(port)
        port.dependant.add(field, self.port, typ)

        status = port.dependant.status
        if status != Dependant.RESOLV:
          self._count += 1
      else:
        port = None

    if port is None or status == Dependant.FAILURE:
      self.failed = True
      if not self.port.dependant.failed():
        self.port.dependant.status_changed()
    if self._loading == 0:
      self.port.dependancy_loaded()

  def get(self, typ=None):
    """Retrieve a list of dependancies."""
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
    """Check the dependancy status for a given stage."""
    # DependHandler status might change without Port's changing
    for i in Dependancy.STAGE2DEPENDS[stage]:
      for j in self._dependancies[i]:
        status = j.dependant().status()
        if status != Dependant.RESOLV:
          return False
    return True

  def update(self, depend):
    """Called when a dependancy has changes status."""
    status = depend.status
    if status == Dependant.FAILURE:
      self.failed = True
      if not self.port.dependant.failed:
        self.port.dependant.status_changed()
      delta = -1
    elif status == Dependant.RESOLV:
      delta = 1
    else: # depend.status() == DependHandler.UNRESOLV
      delta = -1

    self._count -= delta * \
                  len([i for i in sum(self._dependancies, []) if i == depend])
    if self._count < 0:
      self._count = 0
    if not self._count:
      # Check that we do actually have all the dependancies met
      # TODO: Remove, debug check
      for i in self.get():
        if i.dependant.status != Dependant.RESOLV:
          self._count += 1
