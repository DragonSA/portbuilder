"""FreeBSD specific module to get port information."""

from __future__ import absolute_import

import os
import re
import subprocess

from libpb import env, job, log, make, queue, signal

__all__ = ["Attr", "attr", "cache", "clean", "load_defaults"]


def load_defaults():
    """
    Load the defaults as specified from /etc/make.conf.

    Requires flags["chroot"] and env.env to be initialised.
    """
    menv = [
            # DEPENDS_TARGET modifiers
            "DEPENDS_CLEAN", "DEPENDS_PRECLEAN", "DEPENDS_TARGET",
            # Sundry items
            "BATCH", "USE_PACKAGE_DEPENDS", "WITH_DEBUG", "WITH_PKGNG"
        ]

    master_keys = env.env_master.keys()
    keys = set(menv + master_keys)

    args = ["make", "-f/dev/null"] + ["-V%s" % i for i in keys]
    args += ["-D%s" % k if v is True else "%s=%s" % (k, v)
                                                  for k, v in env.env.items()]
    if env.flags["chroot"]:
        args = ["chroot", env.flags["chroot"]] + args
    pmake = subprocess.Popen(args, stdin=subprocess.PIPE, close_fds=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pmake.stdin.close()
    pmake.stderr.close()
    if pmake.wait() == 0:
        make_env = dict((i, j.strip())
                               for i, j in zip(keys, pmake.stdout.readlines()))
    else:
        make_env = dict((i, "") for i in keys)

    # Update env_master with predefined values from make.conf
    for k in master_keys:
        if k in env.env:
            env.env_master[k] = None
        elif make_env[k]:
            env.env[k] = env.env_master[k] = make_env[k]
        else:
            env.env[k] = env.env_master[k]

    # DEPENDS_TARGET / flags["target"] modifiers
    if make_env["DEPENDS_TARGET"]:
        env.flags["target"] = make_env["DEPENDS_TARGET"].split()
        for i in env.flags["target"]:
            if i == "reinstall":
                i = env.flags["target"][env.flags["target"].find(i)] = "install"
            if i not in env.TARGET:
                raise ValueError("unsupported DEPENDS_TARGET: '%s'" % i)
        if "install" not in env.flags["target"] and \
                "package" not in env.flags["target"]:
            raise ValueError("DEPENDS_TARGET must have install or package")
    else:
        if make_env["DEPENDS_CLEAN"] and env.flags["target"][-1] != "clean":
            env.flags["target"] = env.flags["target"] + ["clean"]
        if make_env["DEPENDS_PRECLEAN"] and env.flags["target"][0] != "clean":
            env.flags["target"] = ["clean"] + env.flags["target"]

    # Sundry items
    if make_env["BATCH"]:
        env.flags["config"] = "none"
    if make_env["USE_PACKAGE_DEPENDS"]:
        env.flags["method"] = ["package", "build"]
    if make_env["WITH_DEBUG"]:
        env.flags["debug"] = True
    if make_env["WITH_PKGNG"]:
        env.flags["pkg_mgmt"] = "pkgng"


def clean():
    """Clean the env and os.environ.."""
    # Cleanup some env variables
    if env.env["PORTSDIR"][-1] == '/':
        env.env["PORTSDIR"] = env.env["PORTSDIR"][:-1]

    # Make sure environ is not polluted with make flags
    for key in ("__MKLVL__", "MAKEFLAGS", "MAKELEVEL", "MFLAGS",
                "MAKE_JOBS_FIFO", "SHLVL"):
        try:
            del os.environ[key]
        except KeyError:
            pass


def cache():
    """Cache commonly used variables. which are expensive to compute."""
    # Variables conditionally set in ports/Mk/bsd.port.mk
    uname = os.uname()
    if "ARCH" not in os.environ:
        os.environ["ARCH"] = uname[4]
    if "OPSYS" not in os.environ:
        os.environ["OPSYS"] = uname[0]
    if "OSREL" not in os.environ:
        os.environ["OSREL"] = uname[2].split('-', 1)[0].split('(', 1)[0]
    if "OSVERSION" not in os.environ:
        os.environ["OSVERSION"] = _get_os_version()
    if (uname[4] in ("amd64", "ia64") and
        "HAVE_COMPAT_IA32_KERN" not in os.environ):
        # TODO: create ctypes wrapper around sysctl(3)
        has_compact = "YES" if _sysctl("compat.ia32.maxvmem") else ""
        os.environ["HAVE_COMPAT_IA32_KERN"] = has_compact
    if "LINUX_OSRELEASE" not in os.environ:
        os.environ["LINUX_OSRELEASE"] = _sysctl("compat.linux.osrelease")
    if "UID" not in os.environ:
        os.environ["UID"] = str(os.getuid())
    if "CONFIGURE_MAX_CMD_LEN" not in os.environ:
        os.environ["CONFIGURE_MAX_CMD_LEN"] = _sysctl("kern.argmax")

    # Variables conditionally set in ports/Mk/bsd.port.subdir.mk
    if "_OSVERSION" not in os.environ:
        os.environ["_OSVERSION"] = uname[2]


def attr(origin):
    """Retrieve a ports attributes by using the attribute queue."""
    # TODO inline function to caller
    log.debug("attr()", "Port '%s': getting attribute" % origin)
    attr_obj = Attr(origin)
    queue.attr.add(job.AttrJob(attr_obj))
    return attr_obj


class Attr(signal.Signal):
    """Get the attributes for a given port"""

    def __init__(self, origin):
        super(Attr, self).__init__()
        self.origin = origin

    def get(self):
        """Get the attributes from the port by invoking make"""
        args = []  #: Arguments to be passed to the make target
        # Pass all the arguments from ports_attr table
        for i in ports_attr.itervalues():
            args.append('-V')
            args.append(i[0])

        pmake = make.make_target(self.origin, args, True)
        return pmake.connect(self.parse_attr)

    def parse_attr(self, pmake):
        """Parse the attributes from a port and call the requested function."""
        # TODO: if pmake.wait() != make.SUCCESS
        if pmake.wait() != 0:
            log.error("Attr.parse_attr()",
                      "Failed to get port %s attributes (err=%s)\n%s" %
                          (self.origin, pmake.returncode,
                           "".join(pmake.stderr.readlines())))
            self.emit(self.origin, None)
            return

        errs = pmake.stderr.readlines()
        if len(errs):
            log.error("Attr.parse_attr()",
                      "Non-fatal errors in port %s attributes\n%s" %
                          (self.origin, "".join(errs)))

        attr_map = {}
        for name, value in ports_attr.iteritems():
            if value[1] is str:
                # Get the string (stripped)
                attr_map[name] = pmake.stdout.readline().strip()
            else:
                # Pass the string through a special processor (like list/tuple)
                attr_map[name] = value[1](pmake.stdout.readline().split())
            # Apply all filters for the attribute
            for i in value[2:]:
                try:
                    attr_map[name] = i(attr_map[name])
                except BaseException, e:
                    log.error("Attr.parse_attr()",
                              "Failed to process port %s attributes: %s" %
                                  (self.origin, str(e)))
                    self.emit(self.origin, None)
                    return

        # Process the global option filters
        for fltr in ports_fltr:
            fltr(attr_map)

        self.emit(self.origin, attr_map)


def _sysctl(name):
    """Retrieve the string value of a sysctlbyname(3)."""
    # TODO: create ctypes wrapper around sysctl(3)
    sysctl = subprocess.Popen(("sysctl", "-n", name), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, close_fds=True)
    if sysctl.wait() == 0:
        return sysctl.stdout.read()[:-1]
    else:
        return ""


def _get_os_version():
    """Get the OS Version.  Based on how ports/Mk/bsd.port.mk sets OSVERSION"""
    # XXX: platform specific code
    for path in (env.flags["chroot"] + "/usr/include/sys/param.h",
                 env.flags["chroot"] + "/usr/src/sys/sys/param.h"):
        if os.path.isfile(path):
            # We have a param.h
            osversion = re.search('^#define\s+__FreeBSD_version\s+([0-9]*).*$',
                                open(path, "r").read(), re.MULTILINE)
            if osversion:
                return osversion.groups()[0]
    return _sysctl("kern.osreldate")

#=============================================================================#
#                          PORTS ATTRIBUTE SECTION                            #
#=============================================================================#
ports_attr = {
# Port naming
"name":       ["PORTNAME",     str], # The port's name
"version":    ["PORTVERSION",  str], # The port's version
"revision":   ["PORTREVISION", str], # The port's revision
"epoch":      ["PORTEPOCH",    str], # The port's epoch
"uniquename": ["UNIQUENAME",   str], # The port's unique name

# Port's package naming
"pkgname":   ["PKGNAME",       str], # The port's package name
"pkgprefix": ["PKGNAMEPREFIX", str], # The port's package prefix
"pkgsuffix": ["PKGNAMESUFFIX", str], # The port's package suffix
"pkgfile":   ["PKGFILE",       str], # The port's package file

# Port's dependencies and conflicts
"depends":        ["_DEPEND_DIRS",    tuple], # The port's dependency list
"depend_build":   ["BUILD_DEPENDS",   tuple], # The port's build dependencies
"depend_extract": ["EXTRACT_DEPENDS", tuple], # The port's extract dependencies
"depend_fetch":   ["FETCH_DEPENDS",   tuple], # The port's fetch dependencies
"depend_lib":     ["LIB_DEPENDS",     tuple], # The port's library dependencies
"depend_run":     ["RUN_DEPENDS",     tuple], # The port's run dependencies
"depend_patch":   ["PATCH_DEPENDS",   tuple], # The port's patch dependencies
"depend_package": ["PKG_DEPENDS",     tuple], # The port's package dependencies

# Sundry port information
"category":   ["CATEGORIES", tuple],              # The port's categories
"descr":      ["_DESCR",     str],                # The port's description file
"comment":    ["COMMENT",    str],                # The port's comment
"maintainer": ["MAINTAINER", str],                # The port's maintainer
"options":    ["COMPLETE_OPTIONS_LIST", tuple],  # The port's options
"_options":   ["PORT_OPTIONS",           tuple],  # The port's active options
"prefix":     ["PREFIX",                 str],    # The port's install prefix

# Distribution information
"distfiles": ["DISTFILES",    tuple], # The port's distfiles
"distdir":   ["_DISTDIR",      str],   # The port's distfile's sub-directory
"distinfo":  ["DISTINFO_FILE", str],   # The port's distinfo file

# MAKE_JOBS flags
"jobs_safe":    ["MAKE_JOBS_SAFE",    bool], # Port supports make jobs
"jobs_unsafe":  ["MAKE_JOBS_UNSAFE",  bool], # Port doesn't support make jobs
"jobs_force":   ["FORCE_MAKE_JOBS",   bool], # Force make jobs
"jobs_disable": ["DISABLE_MAKE_JOBS", bool], # Disable make jobs
"jobs_number":  ["_MAKE_JOBS",        str],  # Number of make jobs requested

# Various restrictions
"conflict":   ["CONFLICTS",  tuple],  # Ports this one conflicts with
"no_package": ["NO_PACKAGE", bool],   # Packages distribution restricted

# Sundry information
"interactive": ["IS_INTERACTIVE", bool],  # The port is interactive
"makefiles":   [".MAKEFILE_LIST", tuple], # The Makefiles included
"optionsfile": ["OPTIONSFILE",    str],   # The options file
"pkgdir":      ["PKGREPOSITORY",  str],   # The package directory
"wrkdir":      ["WRKDIR",         str],   # The ports working directory
} #: The attributes of the given port

ports_fltr = []  # Clean-up functions for the ports attributes

# The following are 'fixes' for various attributes
ports_attr["depends"].append(lambda x: [i[len(env.env["PORTSDIR"]) + 1:]
                                                                   for i in x])
ports_attr["depends"].append(lambda x: ([x.remove(i) for i in x
                                         if x.count(i) > 1], x)[1])
ports_attr["distfiles"].append(lambda x: [i.split(':', 1)[0] for i in x])


def parse_jobs_number(jobs_number):
    """Convert jobs number into a number."""
    if not jobs_number:
        return 1
    try:
        return int(jobs_number[2:])
    except ValueError:
        return env.CPUS
ports_attr["jobs_number"].append(parse_jobs_number)


def strip_depends(depends):
    """Remove $PORTSDIR from dependency paths."""
    for depend in depends:
        if depend.find(':') == -1:
            raise RuntimeError("bad dependency line: '%s'" % depend)
        obj, port = depend.split(':', 1)
        if port.startswith(env.env["PORTSDIR"]):
            port = port[len(env.env["PORTSDIR"]) + 1:]
        else:
            raise RuntimeError("bad dependency line: '%s'" % depend)
        yield obj, port
ports_attr["depend_build"].extend((strip_depends, tuple))
ports_attr["depend_extract"].extend((strip_depends, tuple))
ports_attr["depend_fetch"].extend((strip_depends, tuple))
ports_attr["depend_lib"].extend((strip_depends, tuple))
ports_attr["depend_run"].extend((strip_depends, tuple))
ports_attr["depend_patch"].extend((strip_depends, tuple))
ports_attr["depend_package"].extend((strip_depends, tuple))
ports_attr["makefiles"].append(lambda x: [i for i in x if i != '..'])


def ports_options(attr):
    """Convert _COMPLETE_OPTIONS_LIST and PORT_OPTIONS into an option dict."""
    options = {}
    for opt in attr["options"]:
        options[opt] = "on" if opt in attr["_options"] else "off"
    attr["options"] = options
    del attr["_options"]
ports_fltr.append(ports_options)
