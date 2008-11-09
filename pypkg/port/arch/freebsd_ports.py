"""
The FreeBSD module.  This module contains all code specific to the FreeBSD Ports
infrastructure.
"""
from __future__ import absolute_import

from pypkg.make import env

__all__ = ['get_status', 'get_attr']

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
"distfiles": ["_DISTFILES",   tuple], # The port's distfiles
"distdir":   ["_DISTDIR", str],       # The port's distfile's sub-directory

"depends":      ["_DEPEND_DIRS", tuple],   # The ports dependants
"makefiles":    [".MAKEFILE_LIST", tuple], # The makefiles included
"optionsfile":  ["OPTIONSFILE", str],      # The options file
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
ports_attr["makefiles"].append(lambda x: [i for i in x if i != '..'])

del strip_depends

def get_status(origin):
  """
     Get the current status of a port.  A port is either ABSENT, OLDER, CURRENT
     or NEWER.

     @param origin: The origin of the port queried
     @type origin: C{str}
     @return: The port's status
     @rtype: C{int}
  """
  from subprocess import Popen, PIPE, STDOUT

  from pypkg.port import Port  # TODO: Change to ``from .. import Port''

  pkg_version = Popen(['pkg_version', '-O', origin], close_fds=True,
                      stdout=PIPE, stderr=STDOUT)
  if pkg_version.wait() != 0:
    return Port.ABSENT

  info = []
  for i in pkg_version.stdout.readlines():
    if not i.startswith("pkg_version: "):
      info.append(i[:-1])
  
  if len(info) > 1:
    from logging import getLogger
    getLogger('pypkg.port.arch.freebsd_port.port_status').warning(
                                "Multiple ports with same origin '%s'" % origin)

  info = info[0].split()[1]
  if info == '<':
    return Port.OLDER
  elif info == '>':
    return Port.NEWER
  else: #info == '=' or info == '?' or info =='*'
    return Port.CURRENT

def get_attr(origin):
  """
     Retrieves the attributes for a given port.

     @param origin: The port identifier
     @type origin: C{str}
     @return: A dictionary of attributes
     @rtype: C{\{str:str|(str)|\}}
  """
  from pypkg.make import make_target, SUCCESS

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
