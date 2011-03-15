#!/usr/bin/env python
"""Controller for various ports operations."""

VAR_NAME = "^[a-zA-Z_][a-zA-Z0-9_]*$"

class PortDelegate(object):
  """Choose if a port should be build and with which builder."""

  def __init__(self, package, upgrade):
    """Initialise port delegate."""
    self.package = package
    self.upgrade = upgrade
    self.no_port = []

  def __call__(self, port):
    """Add a port to the required builder."""
    from pyport.env import flags

    if isinstance(port, str):
      self.no_port.append(port)
      return
    if not flags["mode"] == "recursive":
      if self.upgrade:
        if port.install_status >= port.CURRENT:
          return
        else:
          port.dependant.status = port.dependant.UNRESOLV
      elif port.install_status > port.ABSENT:
        return
    if self.package:
      from pyport.builder import package_builder
      package_builder(port)
    else:
      from pyport.builder import install_builder
      install_builder(port)

def sigterm(_sig, _frame):
  """Kill subprocesses and die."""
  from pyport import stop
  stop(kill=True, kill_clean=True)
  exit(254)

def sigint(_sig, _frame):
  """Ask politely for everything to stop at a convenient time."""
  from signal import signal, SIGINT
  from pyport.event import post_event
  from pyport import stop
  post_event(stop)
  signal(SIGINT, sigterm)

def main():
  """The main event loop."""
  from signal import signal, SIGINT, SIGTERM
  from pyport.env import flags
  from pyport.monitor import Top
  from pyport.port import get_port

  # Process arguments
  parser = gen_parser()
  options, args = parser.parse_args()
  options.args = args
  options.parser = parser
  set_options(options)

  if len(args) == 0:
    print parser.get_usage()
    return

  # Make sure log_dir is available
  mkdir(flags["log_dir"])

  # Install signal handlers
  signal(SIGINT, sigint)
  signal(SIGTERM, sigterm)

  # Port delegate
  delegate = PortDelegate(options.package, options.upgrade)

  # Execute the primary build target
  for port in args:
    get_port(port, delegate)

  if not flags["no_op_print"]:
    Top().start()
  run_loop(delegate.no_port)

def mkdir(directory):
  """Make a given directory if needed."""
  from os.path import exists, isdir
  from os import mkdir

  if exists(directory):
    if not isdir(directory):
      print "%s: not a directory" % directory
      exit(1)
  else:
    try:
      mkdir(directory)
    except OSError, e:
      print "%s: unable to create directory (%s)" % (directory, e)
      exit(2)

def run_loop(no_port):
  """Run the main event loop, print nice messages if something goes wrong."""
  from pyport.event import run

  try:
    run()

    if no_port:
      print "Unable to locate ports: %s" % no_port
  except SystemExit:
    raise
  except BaseException:
    from sys import stderr
    from traceback import format_list, print_exc
    from pyport.event import traceback

    for tb, name in traceback():
      stderr.write("Traceback from %s (most recent call last):\n" % name)
      stderr.write("%s\n" % "".join(format_list(tb)))
    print_exc()
    exit(255)

def gen_parser():
  """Create the options parser object."""
  from optparse import OptionParser

  usage = "\t%prog [-bdnpruFN] [-c config] [-D variable] [-f file] "\
          "[variable=value] port ..."

  parser = OptionParser(usage, version="%prog 0.1.0")

  parser.add_option("--arch", action="store", type="string", default="",
                    help="Set the architecture environment variables (for "\
                    "cross building)")

  parser.add_option("-b", "--batch", dest="batch", action="store_true",
                    default=False, help="Batch mode.  Skips the config stage.")

  parser.add_option("-c", "--config", action="callback", callback=parse_config,
                    type="string", help="Specify which ports to configure "\
                    "(none, all, newer, changed) [default: changed]")

  parser.add_option("-C", dest="chroot", action="store", type="string",
                    default="", help="Build ports in chroot environment.")

  parser.add_option("-d", "--debug", action="store_true", default=True,
                    help="Turn on extra diagnostic information (slower)")

  parser.add_option("-D", dest="make_env", action="append", metavar="variable",
                    default=[], help="Define the given variable for make (i.e."\
                    " add ``-D variable'' to the make calls.")

  #parser.add_option("-i", "--install", action="store_true", default=True,
                    #help="Install mode.  Installs the listed ports (and any " \
                    #"dependancies required [default].")

  parser.add_option("-f", "--ports-file", dest="ports_file", action="store",
                    type="string", default=False, help="Use ports from file.")

  parser.add_option("-F", "--fetch-only", dest="fetch", action="store_true",
                    default=False, help="Only fetch the distribution files for"\
                    " the ports")

  parser.add_option("-n", dest="no_opt_print", action="store_true",
                    default=False, help="Display the commands that would have "\
                    "been executed, but do not actually execute them.")

  parser.add_option("-N", dest="no_opt", action="store_true", default=False,
                    help="Do not execute any commands.")

  parser.add_option("-p", "--package", action="store_true", default=False,
                    help="Create packages for specified ports.")

  parser.add_option("-P", "--package-all", dest="packageA", action="store_true",
                    default=False, help="Create packages for all installed "\
                    "ports")

  parser.add_option("-u", "--upgrade", action="store_true", default=False,
                    help="Upgrade specified ports.")

  parser.add_option("-U", "--upgrade-all", dest="upgradeA", action="store_true",
                    default=False, help="Upgrade specified ports and all its "\
                    "dependancies.")

  #parser.add_option("--index", action="store_true", default=False,
                    #help="Create the INDEX file for the ports infrastructure.")
  return parser

def set_options(options):
  """Set all the global options."""
  from re import match
  from pyport.env import env, flags

  # Architecture flag
  if options.arch:
    from os import environ
    environ["UNAME_m"] = options.arch
    environ["UNAME_p"] = options.arch
    environ["MACHINE"] = options.arch

  # Batch mode
  if options.batch:
    env["BATCH"] = True

  # Set chroot environment
  if options.chroot:
    from os.path import isdir
    if options.chroot[-1] == '/':
      options.chroot = options.chroot[:-1]
    if not isdir(options.chroot):
      options.parser.error("chroot needs to be a valid directory")
    flags["chroot"] = options.chroot

  # Debug mode
  if options.debug:
    flags["debug"] = True

  # Add all -D options
  for i in options.make_env:
    if not match(VAR_NAME, i):
      options.parser.error("incorrectly formatted variable name: %s" % i)
    env[i] = True

  # Add other make env options (aka variable=value)
  for i in options.args[:]:
    if i.find('=') != -1:
      var, val = i.split('=', 1)
      if not match(VAR_NAME, var):
        options.parser.error("incorrectly formatted variable name: %s" % var)
      env[var] = val
      options.args.remove(i)

  # Fetch only options:
  if options.fetch:
    from pyport.env import cpus
    from pyport.queue import checksum_queue

    flags["fetch_only"] = True
    checksum_queue.load = cpus

  # Fetch ports list from file
  if options.ports_file:
    try:
      options.args.extend(read_port_file(options.ports_file))
    except IOError:
      options.parser.error("unable to open file: %s" % options.ports_file)

  # ! (-n & -N)
  if options.no_opt and options.no_opt_print:
    options.parser.error("-n and -N are mutually exclusive")

  # No operations and print (-n)
  if options.no_opt_print:
    flags["no_op"] = True
    flags["no_op_print"] = True

  # No opterations (-N)
  if options.no_opt:
    flags["no_op"] = True

  # Package all installed ports
  if options.packageA:
    flags["package"] = True
    options.package = True

  # Upgrade all ports
  if options.upgradeA:
    flags["upgrade"] = True
    options.upgrade = True

  # Upgrade ports
  if options.upgrade:
    flags["mode"] = "recursive"

def read_port_file(ports_file):
  """Get ports from a file."""
  ports = []
  for i in open(ports_file, "r"):
    try:
      i = i[:i.index('#')]
    except ValueError:
      pass
    ports.extend(i.split())
  return ports

def parse_config(_option, _opt_str, value, _parser):
  """Set the config requirements."""
  from pyport.env import flags

  if value not in ("none", "all", "newer", "changed"):
    from optparse import OptionValueError
    raise OptionValueError("config must be one of (none, all, newer, changed)")
  flags["config"] = value

if __name__ == "__main__":
  main()
