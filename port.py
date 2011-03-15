#!/usr/bin/env python
"""Controller for various ports operations."""

no_port = []

VAR_NAME = "^[a-zA-Z_][a-zA-Z0-9_]*$"

def port_install(port):
  """Install the port,"""
  from pyport.builder import install_builder

  if not isinstance(port, str) and port.install_status == port.ABSENT:
    install_builder(port)
  else:
    no_port.append(port)

def port_upgrade(port):
  """Upgrade the port."""
  from pyport.builder import install_builder

  if not isinstance(port, str) and port.install_status < port.CURRENT:
    port.dependant.status = port.dependant.UNRESOLV
    install_builder(port)
  else:
    no_port.append(port)

def port_force(port):
  """Reinstall the port."""
  from pyport.builder import install_builder

  if not isinstance(port, str):
    install_builder(port)
  else:
    no_port.append(port)

def main():
  """The main event loop."""
  from pyport.env import flags
  from pyport.monitor import Top
  from pyport.port import get_port

  parser = gen_parser()
  options, args = parser.parse_args()
  options.args = args
  set_options(options)

  if len(args) == 0:
    print parser.get_usage()
    return
    
  # Make sure log_dir is available
  mkdir(flags["log_dir"])

  # Execute the primary build target
  for port in args:
    if options.upgrade:
      if options.recursive:
        get_port(port, port_force)
      else:
        get_port(port, port_upgrade)
    else:
      get_port(port, port_install)

  if not flags["no_op_print"]:
    Top().start()
  run_loop()

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

def run_loop():
  """Run the main event loop, print nice messages if something goes wrong."""
  from pyport.event import run

  try:
    run()
  except BaseException:
    from traceback import format_list, print_exc
    from pyport.event import traceback

    for tb, name in traceback():
      print "Traceback from %s (most recent call last):" % name
      print "".join(format_list(tb))
    print_exc()
    exit(255)

def gen_parser():
  """Create the options parser object."""
  from optparse import OptionParser

  usage = "\t%prog [-bnpruFN] [-c config] [-D variable] [-f file] "\
          "[variable=value] port ..."

  parser = OptionParser(usage, version="%prog 0.1.0")

  parser.add_option("-b", "--batch", dest="batch", action="store_true",
                    default=False, help="Batch mode.  Skips the config stage.")

  parser.add_option("-c", "--config", action="callback", callback=parse_config,
                    type="string", help="Specify which ports to configure "\
                    "(none, all, newer, changed) [default: changed]")

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

  parser.add_option("-p", "--package", dest="package", action="store_true",
                    default=False, help="When installing ports, also generate "\
                    "packages (i.e. do a ``make package'').")

  #parser.add_option("-P", dest="pref_package", action="store_true",
                    #default=False, help="Install packages where possible.")

  parser.add_option("-r", "--recursive", dest="recursive", action="store_true",
                    default=False, help="Update ports and their dependancies"\
                    "(requires -u)")

  parser.add_option("-u", "--upgrade", dest="upgrade", action="store_true",
                    default=False, help="Upgrade port mode.")

  #parser.add_option("--index", action="store_true", default=False,
                    #help="Create the INDEX file for the ports infrastructure.")
  return parser

def set_options(options):
  """Set all the global options."""
  from re import match
  from pyport.env import env, flags

  # Batch mode
  if options.batch:
    env["BATCH"] = True

  # Add all -D options
  for i in options.make_env:
    if not match(VAR_NAME, i):
      options.error("incorrectly formatted variable name: %s" % i)
    env[i] = True

  # Add other make env options (aka variable=value)
  for i in options.args[:]:
    if i.find('=') != -1:
      var, val = i.split('=', 1)
      if not match(VAR_NAME, var):
        options.error("incorrectly formatted variable name: %s" % var)
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
      options.error("unable to ope file: %s" % options.ports_file)

  # ! (-n & -N)
  if options.no_opt and options.no_opt_print:
    options.error("-n and -N are mutually exclusive")

  # No operations and print (-n)
  if options.no_opt_print:
    flags["no_op"] = True
    flags["no_op_print"] = True

  # No opterations (-N)
  if options.no_opt:
    flags["no_op"] = True

  # Package installed ports
  if options.package:
    flags["package"] = True

  # -r requires -u
  if options.recursive and not options.upgrade:
    options.error("-r requires -u")

  # Upgrade mode
  if options.recursive and options.upgrade:
    flags["mode"] = "upgrade"

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
