"""
The Monitor module.  This module provides a variaty of displays for the user.
"""
from __future__ import absolute_import

from .threads import Thread

monitor = None

def set_monitor(mon):
  """
     Start a given monitor

     @param monitor: The monitor to start
     @type monitor: C{Monitor}
  """
  global monitor
  if monitor:
    monitor.stop()
  monitor = mon
  monitor.start()

class Monitor(Thread):
  """
     The monitor abstract super class.  All monitors should either inherit
     this class (and override run) or provide the start/stop interface.
  """

  def __init__(self, name="Monitor"):
    """
       Initialise the monitor
    """
    from .threads import Lock

    Thread.__init__(self, name=name)

    self.__delay = 1  #: Delay between monitor iterations
    self.__lock = Lock()  #: Lock, to manage operations
    self.__paused = False  #: If we are pausing
    self.__started = False  #: Indicate if we have started
    self.__stop = False  #: Indicate the stopped status

  def set_delay(self, delay):
    """
       Set the delay for displaying a new line

       @param delay: The delay
       @type delay: C{int}
    """
    self.__delay = delay

  def start(self):
    """
       Start the monitor
    """
    self.__lock.acquire()
    assert self.__started is False
    self.__started = True
    self._init()
    Thread.start(self)

  def stop(self):
    """
       Stop the monitor
    """
    assert self.__started is True
    self.__stop = True
    self.join()
    self._deinit()

  def pause(self, block=True):
    """
       Pause the monitor

       @param block: If must block before pausing
       @type block: C{bool}
    """
    if not self.__lock.acquire(block):
      return False

    assert self.__paused is False

    self.__paused = True
    self._deinit()

    return True

  def resume(self):
    """
       Resume the monitor
    """
    assert self.__paused is True
    self.__paused = False
    self._init()
    self.__lock.release()

  def _sleep(self):
    """
       Sleep for the required time
    """
    from time import sleep

    self.__lock.release()
    if self.__stop:
      return
    sleep(self.__delay)
    if self.__stop:
      return
    self.__lock.acquire()

  def _stopped(self):
    """
       Indicate if the monitor has been stopped

       @return: If the monitor has stopeed
       @rtype: C{bool}
    """
    return self.__stop

  def _init(self):
    """
       Run any initialisation required.  Strictly for subclasses that require
       this special hook.
    """
    pass

  def _deinit(self):
    """
       Run any deinitialisation required.  Strictly for subclasses that require
       this special hook.
    """
    pass

class NoneMonitor(Monitor):
  """
     This monitor is the equivalent to None, used when no monitor is required.
  """

  def run(self):
    """
       We do nothing, just an empty loop.
    """
    while not self._stopped():
      self._sleep()


class Stat(Monitor):
  """
     The stat monitor.  This monitor is modelled after the *stat tools (such as
     iostat and netstat)
  """

  def __init__(self, delay=1):
    """
       Initialise the monitor.

       @param delay:  How often to display a new line
       @type delay: C{int}
    """
    from time import time
    Monitor.__init__(self, "StatMonitor")
    self.set_delay(delay)

    self.__start = time()  #: The time we started

  def run(self):
    """
       Run the monitor.
    """
    from .port import Port
    from . import queue
    from . import target

    count = 20
    options = (False, False, False, False)
    while not self._stopped():
      try:
        count += 1
        old_options = options
        options = (len(queue.ports_queue) != 0, len(target.fetch_builder) != 0,
                len(target.build_builder) != 0 and not Port.fetch_only,
                len(target.install_builder) != 0 and not Port.fetch_only)

        if count > 20 or options != old_options:
          count = 0
          self._print_header(options)

        self._print_line(options)

        self._sleep()
      except KeyboardInterrupt:
        from .exit import terminate
        terminate()
      except BaseException:
        from logging import getLogger
        getLogger('pypkg.monitor').exception("Exception in Stat monitor")

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

  def _print_line(self, options):
    """
      Print a line describing the current state of the build.  Various options
      are used to control what is displayed.

      @param options: Tuple of booleans, indicating which columns to display
      @type options: C{(bool)}
      @param start: The initial time to use.
      @type start: C{int}
    """
    from time import time

    from .port import cache
    from . import queue
    from . import target

    offset = time() - self.__start
    secs, mins, hour = offset % 60, offset / 60 % 60, offset / 60 / 60
    port_q, fetch_q, build_q, install_q = options

    line = [" %02i:%02i:%02i " % (hour, mins, secs)]

    if port_q and not (fetch_q and build_q and install_q):
      line.append(" %3i %5i %5i " % (len(queue.ports_queue),
                                      queue.ports_queue.qsize(),
                                      len(cache)))
    else:
      line.append(" %6i " % len(cache))

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


def get_stage(port, offset=0):
  """
    Get the ports stage name.  If it is 'install' then abreviate to
    'instal' or if it is 'configure' then abreviate to 'config'.

    @param port: The port
    @type port: C{Port}
    @param offset: The stage from this one
    @type offset: C{int}
    @return: The stage's name
    @rtype: C{str}
  """
  from .port import Port

  stage = Port.STAGE_NAME[port.stage() + offset]
  if stage[-1] == 'l':
    return stage[:-1]
  if stage.endswith('ure'):
    return stage[:-3]
  return stage

def get_name(port):
  """
    Get the ports name

    @param port: The port
    @type port: C{Port}
    @return: The name as 'origin (version)'
    @rtype: C{str}
  """
  return '%s (%s)' % (port.origin(), port.attr('pkgname').rsplit('-', 1)[1])

class Top(Monitor):
  """
     The top monitor.  This monitor is modelled after the top(1) utility.
  """

  def __init__(self):
    """
       Initialise the top monitor.
    """
    from time import time
    Monitor.__init__(self, "TopMonitor")

    self._offset = 0
    self.__start = time()
    self._stdscr = None
    self._stats = Statistics()

  def run(self):
    """
       Display various details about the build process.

       @param stdscr: The main window
       @type stdscr: C{Window}
    """
    while not self._stopped():
      try:
        self._stats = Statistics()

        self._stdscr.erase()
        self._update_header(self._stdscr)
        self._update_rows(self._stdscr)
        self._stdscr.move(self._offset, 0)
        self._stdscr.refresh()

        self._sleep()
      except KeyboardInterrupt:
        from .exit import terminate
        terminate()
      except BaseException:
        from logging import getLogger
        getLogger('pypkg.monitor').exception("Exception in Top monitor")

  def _init(self):
    """
       Initialise the curses library.
    """
    from curses import initscr, cbreak, noecho

    self._stdscr = initscr()
    self._stdscr.keypad(1)
    self._stdscr.nodelay(1)
    self._stdscr.clear()
    cbreak()
    noecho()

  def _deinit(self):
    """
       Shutdown the curses library.
    """
    from curses import nocbreak, echo, endwin

    self._stdscr.move(self._stdscr.getmaxyx()[0] - 1, 0)
    self._stdscr.clrtoeol()
    self._stdscr.refresh()

    self._stdscr.keypad(0)
    nocbreak()
    echo()
    endwin()

  def _update_header(self, scr):
    """
       Update the header details.

       @param scr: The window to display the information on
       @type scr: C{Window}
    """
    from time import strftime
    self._offset = 0
    self._update_ports(scr)
    self._update_summary(scr)
    self._update_stage(scr, "Fetch", self._stats.fetch())
    self._update_stage(scr, "Build", self._stats.build())
    self._update_stage(scr, "Install", self._stats.install())

    offset = self._stats.time() - self.__start
    secs, mins, hours = offset % 60, offset / 60 % 60, offset / 60 / 60 % 60
    days = offset / 60 / 60 / 24
    running = "running %i+%02i:%02i:%02i  " % (days, hours, mins, secs)
    running += strftime("%H:%M:%S")
    scr.addstr(0, scr.getmaxyx()[1] - len(running) - 1, running)

  def _update_ports(self, scr):
    """
       Update the ports details.

       @param scr: The window to display the information on
       @type scr: C{Window}
    """
    port_new = self._stats.ports()

    msg = "port count: %i" % port_new[2]
    if port_new[0]:
      if port_new[1]:
        port_new[1] += port_new[0]
        msg += "; retrieving %i (of %i)" % tuple(port_new[:2])
      else:
        msg += "; retrieving %i" % port_new[0]
    scr.addstr(self._offset, 0, msg)

    self._offset += 1

  def _update_summary(self, scr):
    """
       Update the summary information.

       @param scr: The window to display the information on
       @type scr: C{Window}
    """
    summary_new = self._stats.summary()

    ports = sum(summary_new) - summary_new[3]
    if ports:
      msg = "%i port(s) remaining: " % ports

      msgv = []
      stages = ["active", "queued", "pending", "failed"]
      for i in range(len(stages)):
        if summary_new[i]:
          msgv.append("%i %s" % (summary_new[i], stages[i]))

      msg += ", ".join(msgv)

      scr.addstr(self._offset, 0, msg)

      self._offset += 1

  def _update_stage(self, scr, stage_name, stats):
    """
       Update various stage details.

       @param scr: The window to display the information on
       @type scr: C{Window}
       @param stage_name: The stage's name
       @type stage_name: C{str}
       @param stats: The statistics about the stage
       @type stats: C{[int, int, int, int]}
    """

    if sum(stats):
      msg = "%s: " % stage_name
      msgv = []
      stages = ["active", "queued", "pending", "failed"]
      for i in range(len(stages)):
        if stats[i]:
          msgv.append("%i %s" % (stats[i], stages[i]))

      msg += ", ".join(msgv)
      scr.addstr(self._offset, 0, msg)
      self._offset += 1

  def _update_rows(self, scr):
    """
       Update the rows of port information.

       @param scr: The window to display the information on
       @type scr: C{Window}
    """
    active, queued, pending, failed = self._stats.queues()

    scr.addstr(self._offset + 1, 2, 'STAGE   STATE   TIME PORT (VERSION)')

    lines, columns = scr.getmaxyx()
    lines -= self._offset + 2
    offset = self._offset + 2
    for i in range(min(lines, len(active))):
      port = active[i]
      time = port.working()
      if time:
        offtime = self._stats.time() - time
        time = '%3i:%02i' % (offtime / 60, offtime % 60)
      else:
        time = ' ' * 6
      scr.addnstr(offset + i, 0, ' %6s  active %s %s' %
                  (get_stage(port), time, get_name(port)), columns)

    lines -= len(active)
    offset += len(active)
    for i in range(min(lines, len(queued))):
      port = queued[i]
      scr.addnstr(offset + i, 0, ' %6s  queued        %s' %
                  (get_stage(port, 1), get_name(port)), columns)

    lines -= len(queued)
    offset += len(queued)
    for i in range(min(lines, len(pending))):
      port = pending[i]
      scr.addnstr(offset + i, 0, ' %6s pending        %s' %
                  (get_stage(port, 1), get_name(port)), columns)

    lines -= len(pending)
    offset += len(pending)
    for i in range(min(lines, len(failed))):
      port = failed[i]
      scr.addnstr(offset + i, 0, ' %6s  failed        %s' %
                  (get_stage(port), get_name(port)), columns)


class Statistics(object):
  """
      A collection of statistics abouts various queues, builders and ports.
  """

  def __init__(self):
    """
        Collect the statistics
    """
    from time import time

    from .port import cache
    from .queue import ports_queue as ports
    from . import target

    self.__time = time()
    self.__ports = [len(ports), ports.qsize(), len(cache)]

    #self.__config = target.config_builder.stats()
    self.__fetch = target.fetch_builder.stats()
    self.__build = target.build_builder.stats()
    self.__install = target.install_builder.stats()
    self.__queues = self.__get_queues()

    check = sum(self.__fetch, [])
    self.__build[2] = [i for i in self.__build[2] if i not in check]

    check += sum(self.__build, [])
    self.__install[2] = [i for i in self.__install[2] if i not in check]

    self.__fetch = [len(i) for i in self.__fetch]
    self.__build = [len(i) for i in self.__build]
    self.__install = [len(i) for i in self.__install]

  def ports(self):
    """
        The size statistics on the ports.

        @return: A tuple of the sizes (active, queued, total)
        @rtype: C{(int, int, int)}
    """
    return self.__ports

  def fetch(self):
    """
        The size statistics on the fetch state.

        @return: A tuple of the sizes (active, queued, pending, failed)
        @rtype: C{(int, int, int, int)}
    """
    return self.__fetch

  def build(self):
    """
        The size statistics on the build state.

        @return: A tuple of the sizes (active, queued, pending, failed)
        @rtype: C{(int, int, int, int)}
    """
    return self.__build

  def install(self):
    """
        The size statistics on the install state.

        @return: A tuple of the sizes (active, queued, pending, failed)
        @rtype: C{(int, int, int, int)}
    """
    return self.__install

  def queues(self):
    """
        The collated active, queue, pending, failed queues for fetch, build
        and install.

        @return: A tuple of the ports in the queues
        @rtype: C{((Port), (Port), (Port))}
    """
    return self.__queues

  def summary(self):
    """
        The lenght of the queues (see above).

        @return: A tuple of the lengths
        @rtype: C{(int, int, int)}
    """
    return tuple([len(i) for i in self.__queues])

  def time(self):
    """
        The time these statistics were collated

        @return: The time
        @rtype: C{int}
    """
    return self.__time

  def __get_queues(self):
    """
        Collate ordered information about the ports in various queues.
    """
    fetch = self.__fetch
    build = self.__build
    install = self.__install

    active = install[0] + build[0] + fetch[0]
    queued = install[1] + build[1] + fetch[1]
    pending = []
    failed = install[3] + build[3] + fetch[3]
    for i in fetch[2] + build[2] + install[2]:
      if i not in active and i not in queued and i not in pending:
        pending.append(i)
    pending.reverse()

    return [active, queued, pending, failed]
