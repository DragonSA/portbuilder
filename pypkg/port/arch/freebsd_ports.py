"""
The FreeBSD module.  This module contains all code specific to the FreeBSD Ports
infrastructure.
"""
from __future__ import absolute_import, with_statement

from logging import getLogger

from ...threads import Lock
from ...make import env

__all__ = ['get_status', 'get_attr']

#: Logger for get_attr
log_attr = getLogger('pypkg.port.arch.freebsd_port.get_attr')
#: Logger for get_status
log_status = getLogger('pypkg.port.arch.freebsd_port.port_status')

ports_attr = {
# Port naming
"name":       ["PORTNAME",     str], # The port's name
"version":    ["PORTVERSION",  str], # The port's version
"revision":   ["PORTREVISION", str], # The port's revision
"epoch":      ["PORTEPOCH",    str], # The port's epoch
"uniquename": ["UNIQUENAME", str], # The port's unique name

# Port's package naming
"pkgname": ["PKGNAME",       str], # The port's package name
"prefix":  ["PKGNAMEPREFIX", str], # The port's package prefix
"suffix":  ["PKGNAMESUFFIX", str], # The port's package suffix

# Port's dependancies and conflicts
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
"distfiles": ["_DISTFILES",   tuple], # The port's distfiles
"distdir":   ["_DISTDIR", str],       # The port's distfile's sub-directory

# MAKE_JOBS flags
"jobs_safe":    ["MAKE_JOBS_SAFE",    bool], # Port supports make jobs
"jobs_unsafe":  ["MAKE_JOBS_UNSAFE",  bool], # Port doesn't support make jobs
"jobs_force":   ["FORCE_MAKE_JOBS",   bool], # Force make jobs
"jobs_disable": ["DISABLE_MAKE_JOBS", bool], # Disable make jobs
"jobs_number":  ["MAKE_JOBS_NUMBER",  str],  # Number of make jobs requested

# Various restrictions
"conflict":   ["CONFLICTS",  tuple],  # Ports this one conflicts with
"no_package": ["NO_PACKAGE", bool],   # Packages distribution restricted

# Sundry information
"interactive": ["IS_INTERACTIVE", bool],  # The port is interactive
"makefiles":   [".MAKEFILE_LIST", tuple], # The makefiles included
"optionsfile": ["OPTIONSFILE",    str],   # The options file
"pkgdir":      ["PACKAGES",       str],   # The package directory
"wrkdir":      ["WRKDIR",         str],   # The ports working directory
} #: The attributes of the given port

# The following are 'fixes' for various attributes
ports_attr["depends"].append(lambda x: [i[len(env['PORTSDIR']) + 1:] for i in x])
ports_attr["depends"].append(lambda x: ([x.remove(i) for i in x
                                         if x.count(i) > 1], x)[1])
ports_attr["distfiles"].append(lambda x: [i.split(':', 1)[0] for i in x])

strip_depends = lambda x: [(i.split(':', 1)[0].strip(),
                  i.split(':', 1)[1][len(env['PORTSDIR']) + 1:].strip()) for i in x]
ports_attr["depend_build"].append(strip_depends)
ports_attr["depend_extract"].append(strip_depends)
ports_attr["depend_fetch"].append(strip_depends)
ports_attr["depend_lib"].append(strip_depends)
ports_attr["depend_run"].append(strip_depends)
ports_attr["depend_patch"].append(strip_depends)
ports_attr["makefiles"].append(lambda x: [i for i in x if i != '..'])

del strip_depends

def get_status(origin, attr, changed=False, cache=dict(), lock=Lock("GetStatus")):
  """
     Get the current status of a port.  A port is either ABSENT, OLDER, CURRENT
     or NEWER.

     @param origin: The origin of the port queried
     @type origin: C{str}
     @param attr: The attributes of the port
     @type attr: C{\{str:str|(str)|\}}
     @param changed: Hint that a port has changed (i.e. invalidate cache)
     @type changed: C{bool}
     @param cache: The cache of ports installed
     @type cache: C{\{str:[str]|str|int\}}
     @param lock: The lock for the cache
     @type lock: C{Lock}
     @return: The port's status
     @rtype: C{int}
  """
  from os import path
  from os import listdir

  from ..port import Port

  pkg = "/var/db/pkg"  #: The path to the pkg database
  with lock:
    # If the cached pkg list is old or non-existant update it
    if changed or not cache.has_key('mtime') or path.getmtime(pkg) != cache['mtime']:
      count = 5
      while True:
        try:
          cache['mtime'] = path.getmtime(pkg)
          cache['listdir'] = listdir(pkg)
          break
        except OSError:
          # May happen on occation, retry
          count -= 1
          if not count:
            raise

  status = Port.ABSENT  #: Default status of the port
  name = attr['pkgname'].rsplit('-', 1)[0]  #: The ports name

  for i in cache['listdir']:
    # If the port's name matches that of a database
    if i.rsplit('-', 1)[0] == name:
      content = path.join(pkg, i, '+CONTENTS') #: The pkg's content file
      porigin = None  #: Origin of the package
      try:
        for j in open(content, 'r'):
          if j.startswith('@comment ORIGIN:'):
            porigin = j[16:-1].strip()
            break
          elif j.startswith('@name '):
            if j[6:-1].strip() != i:
              log_status.warn("Package %s has a conflicting name: %s" %
                                                          (i, j[6:-1].strip()))
              porigin = None
              break
      except (IOError, OSError):
        log_status.error("Package has corrupted: %s" % i)

      # If the pkg has the same origin get the maximum of the install status
      if porigin == origin:
        if status > Port.ABSENT:
          log_status.warn("Multiple ports with same origin: %s" % origin)
        status = max(status, cmp_status(attr['pkgname'], i))
      else:
        log_status.warn("Package has same name as %s but with " \
                        "different origin: %s" % (origin, i))
  return status

def get_attr(origin):
  """
     Retrieves the attributes for a given port.

     @param origin: The port identifier
     @type origin: C{str}
     @return: A dictionary of attributes
     @rtype: C{\{str:str|(str)|\}}
  """
  from ...make import make_target, SUCCESS

  # Make sure ports does not end in a trailing slash
  if env['PORTSDIR'][-1] == '/':
    env['PORTSDIR'] = env['PORTSDIR'][:-1]

  args = []  #: Arguments to be passed to the make target
  # Pass all the arguments from ports_attr table
  for i in ports_attr.itervalues():
    args.append('-V')
    args.append(i[0])

  make = make_target(origin, args, pipe=True)
  if make.wait() is not SUCCESS:
    log_attr.error("Error in obtaining information for port: %s" % origin)
    raise RuntimeError("Error in obtaining information for port: %s" % origin)

  attr_map = {}
  for name, value in ports_attr.iteritems():
    if value[1] is str:
      # Get the string (stripped)
      attr_map[name] = make.stdout.readline().strip()
    else:
      # Pass the string through a special processing (like list/tuple)
      attr_map[name] = value[1](make.stdout.readline().split())
    # Apply all filters for the attribute
    for i in value[2:]:
      try:
        attr_map[name] = i(attr_map[name])
      except BaseException:
        log_attr.exception("Exception applying filter for attribute: %s(%s)" %
                                                        (name, attr_map[name]))
        # Rather fail here than mysteriously later
        raise

  return attr_map

def cmp_status(old, new):
  """
     Compare two package names and indicates the difference.

     @param old: The 'old' package name
     @type old: C{str}
     @param new: The 'new' package name
     @type new: C{str}
     @return: Which package is newer
     @rtype: C{int}
  """
  from ..port import Port

  oname, old = old.rsplit('-', 1)  # Name and version components of the old pkg
  nname, new = new.rsplit('-', 1)  # Name and version components of the new pkg

  if oname != nname:
    # The packages are not comparable
    return Port.ABSENT

  if old == new:
    # The packages are the same
    return Port.CURRENT

  # Check the ports apoch
  old, new, status = cmp_attr(old, new, ',')
  if status:
    return Port.CURRENT + status

  # Check the ports revision
  old, new, status = cmp_attr(old, new, '_')
  if status:
    return Port.CURRENT + status

  # Check the ports version from left to right
  old = old.split('.')
  new = new.split('.')
  for i in range(min(len(old), len(new))):
    # Try numirical comparison, otherwise use str
    try:
      status = cmp(int(old[i]), int(new[i]))
    except ValueError:
      status = cmp(old[i], new[i])
    # If there is a difference is leveled version
    if status:
      return Port.CURRENT + status

  # The difference between the number of leveled versioning
  return Port.CURRENT + cmp(len(old), len(new))

def cmp_attr(old, new, attr):
  """
      Compare the two attributes of the port.

      @param old: The 'old' package version
      @type old: C{str}
      @param new: The 'new' package version
      @type new: C{str}
      @param attr: The attr separator:
      @type attr: C{str}
      @return: The stripped package versions and the status
      @rtype: C{(str, str, int)}
  """
  old = old.rsplit(attr, 1)  # The value of the old pkg
  new = new.rsplit(attr, 1)  # The value of the new pkg
  if len(old) > len(new):  # If old has versioning and new does not
    return (old[0], new[0], 1)
  elif len(old) < len(new): # If new has versioning and old does not
    return (old[0], new[0], -1)
  elif len(old) == len(new) == 1:  # If neither has versioning
    return (old[0], new[0], 0)
  else: #if len(old) == 2 and len(new) == 2 # Both have versioning
    return (old[0], new[0], cmp(int(old[1]), int(new[1])))
