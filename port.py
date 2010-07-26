#!/usr/bin/env python
"""
Controller for various ports operations
"""
from logging import getLogger, FileHandler, DEBUG, INFO

from pypkg.env import files
from pypkg import run_main

handler = FileHandler(files['log'], 'w')
handler.setLevel(DEBUG)
log = getLogger('pypkg')
log.addHandler(handler)
log.setLevel(INFO)

getLogger('pypkg.AutoExit').setLevel(DEBUG)

# TODO: Add pylint check for `R0401'

def main():
  """
     The main event loop.  This sets the program on the corrent trajectory and
     then exits.  Everything else just 'runs'
  """
  from pypkg.exit import terminate
  from pypkg.make import set_password
  from pypkg.port import Port, get
  from pypkg import monitor, target

  parser = gen_parser()
  options, args = parser.parse_args()
  options.args = args

  if len(args) == 0:
    print parser.get_usage()
    return

  set_options(options)

  set_password('')

  # Set the monitor
  if not options.no_opt:
    if options.stat_mode:
      if options.stat_mode < 0:
        parser.error("SEC needs to be positive, not %i" % options.stat_mode)
      monitor.set_monitor(monitor.Stat(options.stat_mode))
    else:
      monitor.set_monitor(monitor.Top())

  # Execute the primary build target
  if options.index:
    if len(args):
      parser.error("Ports cannot be specified with --index")
    target.index_builder()
  else:
    callback = target.Caller(len(args), terminate)
    for i in args:
      port = get(i)
      if port:
        if options.fetch:
          target.rfetch_builder(port, callback)
        else:
          status = port.install_status()
          # TODO:
          if (options.install and status == Port.ABSENT) or \
            (not options.install and status < Port.CURRENT):
            target.installer(port, callback)
          else:
            callback()
      else:
        callback()

  return

def gen_parser():
  """
     Create the options parser object

     @return: The options parser
     @rtype: C{OptionParser}
  """
  from optparse import OptionParser

  usage = "\t%prog [-bifnpu] [-w SEC] [-D variable] [variable=value] target ..."

  parser = OptionParser(usage, version="%prog 0.0.4")
  parser.add_option("-b", "--batch", action="store_true", default=False,
                    help="Batch mode.  Skips the config stage.")
  parser.add_option("-D", dest="make_env", action="append", metavar="variable",
                    default=[], help="Define the given variable for make (i.e."\
                    " add ``-D variable'' to the make calls.")
  parser.add_option("-i", "--install", action="store_true", default=True,
                    help="Install mode.  Installs the listed ports (and any " \
                    "dependancies required [default].")
  parser.add_option("-f", "--fetch-only", dest="fetch", action="store_true",
                    default=False, help="Only fetch the distribution files for"\
                    " the ports")
  parser.add_option("-n", dest="no_opt", action="store_true", default=False,
                    help="Display the commands that would have been executed, "\
                    "but do not actually execute them.")
  parser.add_option("-p", "--package", action="store_true", default=False,
                    help="When installing ports, also generate packages (i.e." \
                    " do a ``make package'').")
  parser.add_option("-P", dest="pref_package", action="store_true",
                    default=False, help="Install packages where possible.")
  parser.add_option("-u", "--update", dest="install", action="store_false",
                    default=True, help="Update mode.  Updates the given port." \
                    "  The last -i or -u will be the determining one.")
  parser.add_option("-w", dest="stat_mode", type="int", default=0, metavar="SEC"
                    , help="Use the stats monitor with SEC delay between lines")
  parser.add_option("--index", action="store_true", default=False,
                    help="Create the INDEX file for the ports infrastructure.")
  return parser

def set_options(options):
  """
     Set all the global options.

     @param options: The options
     @type options: C{object}
  """
  from pypkg.make import env, Make
  from pypkg.port import Port

  # Add all -D options
  for i in options.make_env:
    env[i] = None

  # Add other make env options (aka variable=value)
  for i in options.args[:]:
    if i.find('=') != -1:
      # TODO:  Make sure var, val take the correct values
      var, val = i.split('=', 1)
      env[var] = val
      options.args.remove(i)

  # Batch mode, no configuring (-b)
  Port.force_noconfig = options.batch

  # No operations (-n)
  if options.no_opt:
    Make.no_opt = True

  # Package the ports after installing (-p)
  Port.package = options.package

  # Use packages for port and its dependancies
  if options.pref_package:
    from pypkg.target import pkginstall_builder, installer
    installer.use(pkginstall_builder)

run_main(main)
