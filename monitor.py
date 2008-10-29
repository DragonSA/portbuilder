"""
The Monitor module.  This module provides a variaty of displays for the user.
"""

from time import time

LINE = 0  #: Line mode

def monitor(mode):
  """
     Start a given monitor

     @param mode: The monitor to start
     @type mode: C{int}
  """
  from threading import Thread

  target = None
  if mode is LINE:
    target = line_mode
  else:
    from logging import getLogger
    getLogger('pypkg.monitor').error("Unknown monitor code: %i" % mode)

  if target:
    mon = Thread(target=target)
    mon.setDaemon(True)
    mon.start()
    return mon
  else:
    return None

def print_header(options):
  """
     Print the header for various columns.

     @param options: Tuple of booleans, indicating which columns to display
     @type options: C{(bool)}
  """
  port_q, fetch_q, build_q, install_q = options

  head = ([], [])

  # Time display
  head[0].append('   TIME   ')
  head[1].append('          ')

  if port_q and not (fetch_q and build_q and install_q):
    head[0].append('      PORT       ')
    head[1].append(' Act Queue Total ')
  else:
    head[0].append('  PORT  ')
    head[1].append('        ')

  if fetch_q:
    head[0].append('      FETCH      ')
    head[1].append(' Act Queue Total ')

  if build_q:
    head[0].append('      BUILD      ')
    head[1].append(' Act Queue Total ')

  if install_q:
    head[0].append('     INSTALL     ')
    head[1].append(' Act Queue Total ')

  print
  print "|".join(head[0])
  if port_q or fetch_q or build_q or install_q:
    print "|".join(head[1])
  print "+".join(['-' * len(i) for i in head[0]])

def print_line(options, start=time()):
  """
     Print a line describing the current state of the build.  Various options
     are used to control what is displayed.

     @param options: Tuple of booleans, indicating which columns to display
     @type options: C{(bool)}
     @param start: The initial time to use.
     @type start: C{int}
  """
  from port import port_cache
  import queue
  import target

  offset = time() - start
  secs, mins, hour = offset % 60, offset / 60 % 60, offset / 60 / 60
  port_q, fetch_q, build_q, install_q = options

  line = [" %02i:%02i:%02i " % (hour, mins, secs)]

  if port_q and not (fetch_q and build_q and install_q):
    line.append(" %3i %5i %5i " % (len(queue.ports_queue),
                                    queue.ports_queue.qsize(),
                                    len(port_cache)))
  else:
    line.append(" %6i " % len(port_cache))

  if fetch_q:
    line.append(" %3i %5i %5i " % (len(queue.fetch_queue),
                                    queue.fetch_queue.qsize(),
                                    len(target.fetch_builder)))

  if build_q:
    line.append(" %3i %5i %5i " % (len(queue.build_queue),
                                    queue.build_queue.qsize(),
                                    len(target.build_builder)))

  if install_q:
    line.append(" %3i %5i %5i " % (len(queue.install_queue),
                                    queue.install_queue.qsize(),
                                    len(target.install_builder)))

  print "|".join(line)

def line_mode():
  """
     Display progress using the line mode (aka iostat mode)
  """
  from port import Port
  import queue
  from sys import stdout
  import target
  from time import sleep

  count = 20
  options = (False, False, False, False)
  while True:
    try:
      if len(queue.config_queue) and Port.configure:
        sleep(1)
        continue
      count += 1

      old_options = options
      options = (len(queue.ports_queue) != 0, len(target.fetch_builder) != 0,
               len(target.build_builder) != 0 and not Port.fetch_only,
               len(target.install_builder) != 0 and not Port.fetch_only)

      if count > 20 or options != old_options:
        count = 0
        print_header(options)

      print_line(options)

      stdout.flush()
      sleep(1)
    except KeyboardInterrupt:
      from exit import terminate
      terminate()
