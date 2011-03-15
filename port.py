#!/usr/bin/env python
"""Controller for various ports operations."""

def port_install(port):
  from pyport.builder import install_builder

  if not isinstance(port, str) and port.install_status == port.ABSENT:
    install_builder(port)
  else:
    pass
    # TODO: report error

def port_upgrade(port):
  from pyport.builder import install_builder

  if not isinstance(port, str) and port.install_status < port.CURRENT:
    install_builder(port)
  else:
    pass
    # TODO: report error

def port_force(port):
  from pyport.builder import install_builder

  if not isinstance(port, str):
    install_builder(port)
  else:
    pass
    # TODO: report error

def main():
  """The main event loop."""
  from pyport.env import flags
  from pyport.event import run
  from pyport.monitor import Top
  from pyport.port import get_port

  parser = gen_parser()
  options, args = parser.parse_args()
  options.args = args
  set_options(options)

  if len(args) == 0:
    print parser.get_usage()
    return

  # Execute the primary build target
  for port in args:
    if options.upgrade:
      if options.recursive:
        get_port(port, port_force)
      else:
        get_port(port, upgrade)
    else:
      get_port(port, port_install)

  if not flags["no_op_print"]:
    Top().start()
  run()

def gen_parser():
  """Create the options parser object."""
  from optparse import OptionParser

  usage = "\t%prog [-bnNp] [-c config] [-D variable] [variable=value] port ..."

  parser = OptionParser(usage, version="%prog 0.1.0")

  parser.add_option("-b", "--batch", action="store_true", default=False,
                    help="Batch mode.  Skips the config stage.")

  parser.add_option("-c", "--config", action="callback", callback=parse_config,
                    type="string", help="Specify which ports to configure "\
                    "(none, all, newer, changed) [default: changed]")

  parser.add_option("-D", dest="make_env", action="append", metavar="variable",
                    default=[], help="Define the given variable for make (i.e."\
                    " add ``-D variable'' to the make calls.")

  #parser.add_option("-i", "--install", action="store_true", default=True,
                    #help="Install mode.  Installs the listed ports (and any " \
                    #"dependancies required [default].")

  parser.add_option("-F", "--fetch-only", dest="fetch", action="store_true",
                    default=False, help="Only fetch the distribution files for"\
                    " the ports")

  parser.add_option("-n", dest="no_opt_print", action="store_true",
                    default=False, help="Display the commands that would have "\
                    "been executed, but do not actually execute them.")

  parser.add_option("-N", dest="no_opt", action="store_true", default=False,
                    help="Do not execute any commands.")

  parser.add_option("-p", "--package", action="store_true", default=False,
                    help="When installing ports, also generate packages (i.e." \
                    " do a ``make package'').")

  #parser.add_option("-P", dest="pref_package", action="store_true",
                    #default=False, help="Install packages where possible.")

  parser.add_option("-r", "--recursive", dest="recursive", action="store_true",
                    default=False, help="Update ports and their dependancies"\
                    "(requires -u)")

  parser.add_option("-u", "--upgrade", dest="upgrade", action="store_true",
                    default=False, help="Upgrade port mode.")

  #parser.add_option("-w", dest="stat_mode", type="int", default=0, metavar="SEC"
                    #, help="Use the stats monitor with SEC delay between lines")
  #parser.add_option("--index", action="store_true", default=False,
                    #help="Create the INDEX file for the ports infrastructure.")
  return parser

def set_options(options):
  """Set all the global options."""
  from pyport.env import env, flags

  # Batch mode
  if options.batch:
    env["BATCH"] = True

  # Add all -D options
  for i in options.make_env:
    env[i] = True

  # Fetch only options:
  if options.fetch:
    flags["fetch_only"] = True

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

  # Add other make env options (aka variable=value)
  for i in options.args[:]:
    if i.find('=') != -1:
      # TODO:  Make sure var, val take the correct values
      var, val = i.split('=', 1)
      env[var] = val
      options.args.remove(i)

def parse_config(option, _opt_str, value, parser):
  from pyport.env import flags

  if value not in ("none", "all", "newer", "changed"):
    from optparse import OptionValueError
    raise OptionValueError("config must be one of (none, all, newer, changed)")
  flags["config"] = value

if __name__ == "__main__":
  main()
