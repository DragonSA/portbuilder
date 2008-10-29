"""
The Monitor module.  This module provides a variaty of displays for the user.
"""
from threading import Thread
from time import time

LINE = 0  #: Line mode

monitor = None

def set_monitor(mon):
  """
     Start a given monitor

     @param monitor: The monitor to start
  """
  global monitor
  if monitor:
    monitor.stop()
  monitor = mon
  monitor.start()

class Stat(Thread):
  """
     The stat monitor.  This monitor is modelled after the *stat tools (such as
     iostat and netstat)
  """

  def __init__(self, delay=1):
    """
       Initialise the monitor

       @param delay:  How often to display a new line
       @type delay: C{int}
    """
    Thread.__init__(self)
    self.__run = True
    self.__delay = delay
    self.setDaemon(True)

  def stop(self):
    """
       Terminate the monitor
    """
    self.__run = False

  def run(self):
    """
       Run the monitor
    """
    from port import Port
    import queue
    from sys import stdout
    import target
    from time import sleep

    count = 20
    options = (False, False, False, False)
    while self.__run:
      try:
        if len(queue.config_queue) and Port.configure:
          sleep(self.__delay)
          continue
        count += 1

        old_options = options
        options = (len(queue.ports_queue) != 0, len(target.fetch_builder) != 0,
                len(target.build_builder) != 0 and not Port.fetch_only,
                len(target.install_builder) != 0 and not Port.fetch_only)

        if count > 20 or options != old_options:
          count = 0
          self._print_header(options)

        self._print_line(options)

        stdout.flush()
        sleep(1)
      except KeyboardInterrupt:
        from exit import terminate
        terminate()

  def set_delay(self, delay):
    """
       Set the delay for displaying a new line

       @param delay: The delay
       @type delay: C{int}
    """
    self.__delay = delay

  @staticmethod
  def _print_header(options):
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

  @staticmethod
  def _print_line(options, start=time()):
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
