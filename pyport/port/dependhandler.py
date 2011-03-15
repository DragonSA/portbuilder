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
    Port.CONFIG:     (),                           # The config dependancies
    Port.CHECKSUM:   (),                           # The checksum dependancies
    Port.FETCH:      (FETCH,),                     # The fetch dependancies
    Port.BUILD:      (EXTRACT, PATCH, LIB, BUILD), # The build dependancies
    Port.INSTALL:    (LIB, RUN),                   # The install dependancies
    Port.PKGINSTALL: (LIB, RUN),                   # The pkginstall dependencies
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
    self._dependants = [[], [], [], [], [], []]  #: All dependants
    self.port = port  #: The port whom we handle
    self.priority = port.priority
    # TODO: Change to actually check if we are resolved
    if port.install_status > Port.ABSENT:
      self.status = Dependant.RESOLV
    else:
      self.status = Dependant.UNRESOLV

  def __repr__(self):
    return "<Dependant(port=%s)>" % self.port.origin

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
      depends = set()
      for i in self._dependants:
        depends.update(j[1] for j in i)
    elif isinstance(typ, int):
      depends = set(j[1] for j in self._dependants[typ])
    else:
      depends = set()
      for i in typ:
        depends.update(j[1] for j in self._dependants[i])

    return depends

  @property
  def failed(self):
    """Shorthand for self.status() == Dependant.FAILURE."""
    return self.status == Dependant.FAILURE

  def status_changed(self):
    """Indicates that our port's status has changed."""
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
    if not self._loading:
      self._update_priority()
      self.port.dependancy_loaded(True)

  def __repr__(self):
    return "<Dependancy(port=%s)>" % self.port.origin

  def _add(self, port, field, typ):
    """Add a port to our dependancy list."""
    self._loading -= 1

    if isinstance(port, str):
      port = False

    if port:
      status = port.dependant.status
      if port not in self._dependancies[typ]:
        self._dependancies[typ].append(port)
        port.dependant.add(field, self.port, typ)

        if status != Dependant.RESOLV:
          self._count += 1

    if not port or status == Dependant.FAILURE:
      self.failed = True
      if not self.port.dependant.failed:
        self.port.dependant.status_changed()
    if self._loading == 0:
      self._update_priority()
      self.port.dependancy_loaded(not self.failed)

  def get(self, typ=None):
    """Retrieve a list of dependancies."""
    if typ is None:
      depends = set()
      for i in self._dependancies:
        depends.update(i)
    elif isinstance(typ, int):
      depends = set(self._dependancies[typ])
    else:
      depends = set()
      for i in typ:
        depends.update(self._dependancies[i])

    return depends

  def check(self, stage):
    """Check the dependancy status for a given stage."""
    # DependHandler status might change without Port's changing
    bad = set()
    for i in Dependancy.STAGE2DEPENDS[stage]:
      for j in self._dependancies[i]:
        status = j.dependant.status
        if status != Dependant.RESOLV:
          bad.add(j)
    return bad

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

  def _update_priority(self):
    """Update the priority of all ports that are affected by this port,"""
    from collections import deque

    update_list = deque()
    updated = set()
    update_list.extend(self.get())
    priority = self.port.dependant.priority
    while len(update_list):
      port = update_list.popleft()
      if port not in updated:
        port.dependant.priority += priority
        if port.dependancy is not None:
          update_list.extend(port.dependancy.get())
        updated.add(port)
