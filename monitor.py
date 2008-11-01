"""
The Monitor module.  This module provides a variaty of displays for the user.
"""
from threading import Thread

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

  def __init__(self):
    """
       Initialise the monitor
    """
    from threading import Lock
    
    Thread.__init__(self)

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

    Thread.__init__(self)

  def stop(self):
    """
       Stop the monitor
    """
    assert self.__started is True
    self.__stop = True
    self.join()

  def pause(self):
    """
       Pause the monitor
    """
    self.__lock.acquire()
    assert self.__paused is False
    self.__paused = True

  def resume(self):
    """
       Resume the monitor
    """
    assert self.__paused is True
    self.__paused = False
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

class NoneMonitor(Monitor):
  """
     This monitor is the equivalent to None, used when no monitor is required
  """

  def run(self):
    """
       We do nothing, just an empty look
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
       Initialise the monitor

       @param delay:  How often to display a new line
       @type delay: C{int}
    """
    from time import time
    Monitor.__init__(self)
    self.set_delay(delay)
    
    self.__start = time()  #: The time we started

  def run(self):
    """
       Run the monitor
    """
    import queue
    import target
    from port import Port

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
        from exit import terminate
        terminate()

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
    import queue
    import target

    from port import cache
    from time import time

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


class Top(Monitor):
  """
     The top monitor.  This monitor is modelled after the top(1) utility.
  """

  def __init__(self):
    """
       Initialise the top monitor
    """
    from time import time
    Monitor.__init__(self)
    
    self.__offset = 0
    self.__start = time()
    self.__stats = Statistics()

  def run(self):
    """
       Run the top monitor, this is done through the curses.wrapper utility
       function
    """
    from curses import wrapper
    wrapper(self._run)

  def _run(self, stdscr):
    """
       Display various details about the build process

       @param stdscr: The main window
       @type stdscr: C{Window}
    """
    from port import Port
    from queue import config_queue

    while not self._stopped():
      try:
        self.__stats = Statistics()

        stdscr.erase()
        self.update_header(stdscr)
        self.update_rows(stdscr)
        stdscr.move(self.__offset, 0)
        stdscr.refresh()
        
        self._sleep()
      except KeyboardInterrupt:
        from exit import terminate
        terminate()

  def update_header(self, scr):
    """
       Update the header details

       @param scr: The window to display the information on
       @type scr: C{Window}
    """
    from time import strftime
    self.__offset = 0
    self.update_ports(scr)
    self.update_summary(scr)
    self.update_stage(scr, "Fetch", Statistics.fetch)
    #self.update_stage(src, "Config", Statistics.config)
    self.update_stage(scr, "Build", Statistics.build)
    self.update_stage(scr, "Install", Statistics.install)

    offset = self.__stats.time() - self.__start
    secs, mins, hours = offset % 60, offset / 60 % 60, offset / 60 / 60 % 60
    days = offset / 60 / 60 / 24
    running = "running %i+%02i:%02i:%02i  " % (days, hours, mins, secs)
    running += strftime("%H:%M:%S")
    scr.addstr(0, scr.getmaxyx()[1] - len(running) - 1, running)

  def update_ports(self, scr):
    """
       Update the ports details

       @param scr: The window to display the information on
       @type scr: C{Window}
    """
    port_new = self.__stats.ports()
    
    msg = "port count: %i" % port_new[2]
    if port_new[0]:
      if port_new[1]:
        msg += "; retrieving %i (of %i)" % port_new[:2]
      else:
        msg += "; retrieving %i/%i" % (port_new[0], port_new[3])
    scr.addstr(self.__offset, 0, msg)

    self.__offset += 1

  def update_summary(self, scr):
    """
       Update the summary information

       @param scr: The window to display the information on
       @type scr: C{Window}
    """
    summary_new = self.__stats.summary()

    ports = sum(summary_new)
    if ports:
      msg = "%i ports:" % ports
      if summary_new[0]:
        msg += " %i active" % summary_new[0]
        if summary_new[1]:
          msg += ", %i queued" % summary_new[1]
        if summary_new[2]:
          msg += ", %i pending" % summary_new[2]
      scr.addstr(self.__offset, 0, msg)

      self.__offset += 1

  def update_stage(self, scr, stage_name, stats):
    """
       Update various stage details

       @param scr: The window to display the information on
       @type scr: C{Window}
       @param stage_name: The stage's name
       @type stage_name: C{str}
       @param stats: A method that returns the stages statistics
       @type stats: C{method}
    """
    stats = list(stats(self.__stats))
    stats[2] -= stats[0] + stats[1]

    if stats[0] or stats[2]:
      msg = "%s: " % stage_name
      if stats[0]:
        if not stats[1]:
          msg += "%i/%i active" % (stats[0], stats[3])
        else:
          msg += "%i active, %i queued" % tuple(stats[0:2])
        if stats[2]:
          msg += ", %i pending" % stats[2]
      elif stats[2]:
        msg += "%i pending" % stats[2]
      scr.addstr(self.__offset, 0, msg)

      self.__offset += 1

  def update_rows(self, scr):
    """
       Update the rows of port information

       @param scr: The window to display the information on
       @type scr: C{Window}
    """
    def get_stage(port, offset=0):
      """
         Get the ports stage name.  If it is 'install' then abreviate to
         'instal' or if it is 'configure' then abreviate to 'config'

         @param port: The port
         @type port: C{Port}
         @param offset: The stage from this one
         @type offset: C{int}
         @return: The stage's name
         @rtype: C{str}
      """
      from port import Port
      
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
    
    active, queued, pending = self.__stats.queues()

    scr.addstr(self.__offset + 1, 2, 'PID  STAGE   STATE   TIME PORT (VERSION)')

    lines, columns = scr.getmaxyx()
    lines -= self.__offset + 2
    offset = self.__offset + 2
    for i in range(min(lines, len(active))):
      port = active[i]
      time = port.working()
      if time:
        offtime = self.__stats.time() - time
        time = '%3i:%02i' % (offtime / 60, offtime % 60)
      else:
        time = ' ' * 6
      scr.addnstr(offset + i, 0, '%5i %6s  active %s %s' %
                  (0, get_stage(port), time, get_name(port)), columns)

    lines -= len(active)
    offset += len(active)
    for i in range(min(lines, len(queued))):
      port = queued[i]
      scr.addnstr(offset + i, 0, '%5i %6s  queued        %s' %
                  (0, get_stage(port, 1), get_name(port)), columns)

    lines -= len(queued)
    offset += len(queued)
    for i in range(min(lines, len(pending))):
      port = pending[i]
      scr.addnstr(offset + i, 0, '%5i %6s pending        %s' %
                  (0, get_stage(port, 1), get_name(port)), columns)
      

class Statistics(object):
  """
      A collection of statistics abouts various queues, builders and ports
  """

  def __init__(self):
    """
        Collect the statistics
    """
    import queue
    import target

    from port import cache
    from time import time

    self.__time = time()
    self.__ports = Statistics.size(queue.ports_queue, cache)
    self.__fetch = Statistics.size(queue.fetch_queue, target.fetch_builder)
    #self.__config = Statistics.size(queue.config_queue,target.config_builder)
    self.__build = Statistics.size(queue.build_queue, target.build_builder)
    self.__install = Statistics.size(queue.install_queue,
                                      target.install_builder)
    self.__queues = Statistics.get_queues()

  def ports(self):
    """
        The size statistics on the ports

        @return: A tuple of the sizes (active, queued, total, workers)
        @rtype: C{(int, int, int, int)}
    """
    return self.__ports

  def fetch(self):
    """
        The size statistics on the fetch state

        @return: A tuple of the sizes (active, queued, total, workers)
        @rtype: C{(int, int, int, int)}
    """
    return self.__fetch

  #def config(self):
    #"""
        #The size statistics on the config state

        #@return: A tuple of the sizes (active, queued, total, workers)
        #@rtype: C{(int, int, int, int)}
    #"""
    #return self.__config

  def build(self):
    """
        The size statistics on the build state

        @return: A tuple of the sizes (active, queued, total, workers)
        @rtype: C{(int, int, int, int)}
    """
    return self.__build

  def install(self):
    """
        The size statistics on the install state

        @return: A tuple of the sizes (active, queued, total, workers)
        @rtype: C{(int, int, int, int)}
    """
    return self.__install

  def queues(self):
    """
        The collated active, queue, pending queus for fetch, (config), build
        and install.

        @return: A tuple of the ports in the queues
        @rtype: C{((Port), (Port), (Port))}
    """
    return self.__queues

  def summary(self):
    """
        The lenght of the queues (see above)

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

  @staticmethod
  def get_queues():
    """
        Collate ordered information about the ports in various queues
    """
    from target import fetch_builder, build_builder, install_builder
      # and config_builder
    fetch = fetch_builder.stats()
    build = build_builder.stats()
    install = install_builder.stats()

    active = install[0] + build[0] + fetch[0]
    queued = install[1] + build[1] + fetch[1]
    pending = []
    for i in fetch[2] + build[2] + install[2]:
      if i not in active and i not in queued:
        pending.append(i)
    pending.reverse()

    return (tuple(active), tuple(queued), tuple(pending))

  @staticmethod
  def size(queue, builder):
    """
        Collect size information about the given queue and builder

        @param queue: The queue for the stage
        @type queue: C{WorkerQueue}
        @param builder: The builder for the stage
        @type builder: C{StageBuilder}
        @return: The size statistics (active, queue, total, workers)
        @rtype: C{(int, int, int, int)}
    """
    return (len(queue), queue.qsize(), len(builder), queue.pool())
