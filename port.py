#!/usr/bin/env python
"""Controller for various ports operations."""

def port_install(port):
  from pyport.builder import install_builder

  if str(port) != str:
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
    get_port(port, port_install)

  if not flags["no_op_print"]:
    Top().start()
  run()

def gen_parser():
  """Create the options parser object."""
  from optparse import OptionParser

  usage = "\t%prog [-nN] [-D variable] [variable=value] port ..."

  parser = OptionParser(usage, version="%prog 0.1.0")
  parser.add_option("-b", "--batch", action="store_true", default=False,
                    help="Batch mode.  Skips the config stage.")
  parser.add_option("-D", dest="make_env", action="append", metavar="variable",
                    default=[], help="Define the given variable for make (i.e."\
                    " add ``-D variable'' to the make calls.")
  #parser.add_option("-i", "--install", action="store_true", default=True,
                    #help="Install mode.  Installs the listed ports (and any " \
                    #"dependancies required [default].")
  #parser.add_option("-f", "--fetch-only", dest="fetch", action="store_true",
                    #default=False, help="Only fetch the distribution files for"\
                    #" the ports")
  parser.add_option("-n", dest="no_opt_print", action="store_true",
                    default=False, help="Display the commands that would have "\
                    "been executed, but do not actually execute them.")
  parser.add_option("-N", dest="no_opt", action="store_true", default=False,
                    help="Do not execute any commands.")
  #parser.add_option("-p", "--package", action="store_true", default=False,
                    #help="When installing ports, also generate packages (i.e." \
                    #" do a ``make package'').")
  #parser.add_option("-P", dest="pref_package", action="store_true",
                    #default=False, help="Install packages where possible.")
  #parser.add_option("-u", "--update", dest="install", action="store_false",
                    #default=True, help="Update mode.  Updates the given port." \
                    #"  The last -i or -u will be the determining one.")
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

  # Add other make env options (aka variable=value)
  for i in options.args[:]:
    if i.find('=') != -1:
      # TODO:  Make sure var, val take the correct values
      var, val = i.split('=', 1)
      env[var] = val
      options.args.remove(i)

  if options.no_opt and options.no_opt_print:
    options.error("-n and -N are mutually exclusive")

  # No operations and print (-n)
  if options.no_opt_print:
    flags["no_op"] = True
    flags["no_op_print"] = True

  # No opterations (-N)
  if options.no_opt:
    flags["no_op"] = True

main()
