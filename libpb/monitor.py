"""Displays about activity."""

from __future__ import absolute_import

from abc import ABCMeta, abstractmethod

__all__ = ["Monitor", "Top"]

class Monitor(object):
  """The monitor abstract super class."""

  __metaclass__ = ABCMeta

  def __init__(self):
    """Initialise the monitor"""
    from .event import alarm

    self.delay = 1  #: Delay between monitor iterations
    self._started = False  #: Indicate if we have started
    self._stopped = False  #: Indicate the stopped status

    alarm(self.alarm, 1)

  def alarm(self, end):
    """Monitor interface for event manager."""
    if not self._started:
      return self.delay
    elif end is None:
      if self._started and not self._stopped:
        self.stop()
    elif end is False:
      if self._stopped:
        self.start()
      else:
        self.run()
    elif not self._stopped:
      self.run()
      self.stop()
    return self.delay

  def start(self):
    """Start the monitor."""
    self._started = True
    self._stopped = False
    self._init()
    self.run()

  def stop(self):
    """Stop the monitor."""
    assert self._started is True
    self._stopped = True
    self._deinit()

  @abstractmethod
  def run(self):
    """Refresh the display."""
    pass

  def _init(self):
    """Run any initialisation required."""
    pass

  def _deinit(self):
    """Run any denitialisation required."""
    pass


STAGE_NAME = ["config", "config", "chcksm", "fetch", "build", "install", "package", "error"]

def get_name(port):
  """Get the ports name."""
  return port.attr["pkgname"]

class Top(Monitor):
  """A monitor modelled after the top(1) utility."""

  def __init__(self):
    """Initialise the top monitor."""
    from time import time
    Monitor.__init__(self)

    self._offset = 0
    self._time = time()
    self._stdscr = None
    self._stats = None

    self._failed_only = False
    self._idle = True
    self._skip = 0
    self._quit = 0

  def run(self):
    """Refresh the display."""
    from .env import flags

    if flags["fetch_only"]:
      self._stats = Statistics(("config", "checksum", "fetch"))
    else:
      self._stats = Statistics()

    self._stdscr.erase()
    self._update_header(self._stdscr)
    self._update_rows(self._stdscr)
    self._stdscr.move(self._offset, 0)
    self._stdscr.refresh()

  def _init(self):
    """Initialise the curses library."""
    from curses import initscr, cbreak, noecho
    from sys import stdin
    from .event import select

    self._stdscr = initscr()
    self._stdscr.keypad(1)
    self._stdscr.nodelay(1)
    self._stdscr.clear()
    cbreak()
    noecho()

    select(self._userinput, rlist=stdin)

  def _deinit(self):
    """Shutdown the curses library."""
    from curses import nocbreak, echo, endwin
    from sys import stdin
    from .event import unselect

    self._stdscr.move(self._stdscr.getmaxyx()[0] - 1, 0)
    self._stdscr.clrtoeol()
    self._stdscr.refresh()

    self._stdscr.keypad(0)
    nocbreak()
    echo()
    endwin()

    unselect(self._userinput, rlist=stdin)

  def _userinput(self):
    """Gte user input and change display options."""
    from curses import KEY_CLEAR, KEY_NPAGE, KEY_PPAGE, ascii

    run = False
    while True:
      ch = self._stdscr.getch()
      if ch == -1:
        break
      elif ch == ord('f'):                         # Toggle fetch only display
        self._failed_only = not self._failed_only
      elif ch == ord('i') or ch == ord('I'):       # Toggle showing idle
        self._idle = not self._idle
      elif ch == ord('q'):                         # Quit
        from . import stop

        self._quit += 1
        if self._quit == 1:
          stop()
        elif self._quit == 2:
          stop(kill=True)
        elif self._quit == 3:
          stop(kill=True, kill_clean=True)
          exit(254)
        continue
      elif ch == KEY_CLEAR or ch == ascii.FF:      # Redraw window
        self._stdscr.clear()
      elif ch == KEY_PPAGE:                        # Page up display
        self._skip -= self._stdscr.getmaxyx()[0] - self._offset - 2
        self._skip = max(0, self._skip)
      elif ch == KEY_NPAGE:                        # Page down display
        self._skip += self._stdscr.getmaxyx()[0] - self._offset - 2
      else:                                        # Unknown input
        continue
      run = True
    if run:
      # Redraw display if required
      self.run()

  def _update_header(self, scr):
    """Update the header details."""
    from time import strftime
    from .event import pending_events

    self._offset = 0
    self._update_ports(scr)
    self._update_summary(scr)
    self._update_stage(scr, "Checksum", self._stats.checksum)
    self._update_stage(scr, "Fetch", self._stats.fetch)
    self._update_stage(scr, "Build", self._stats.build)
    self._update_stage(scr, "Install", self._stats.install)
    self._update_stage(scr, "Package", self._stats.package)

    offset = self._stats.time - self._time
    secs, mins, hours = offset % 60, offset / 60 % 60, offset / 60 / 60 % 60
    days = offset / 60 / 60 / 24
    # Display running time
    running = "running %i+%02i:%02i:%02i  " % (days, hours, mins, secs)
    # Display current time
    running += strftime("%H:%M:%S")
    if pending_events():
      # Display pending events
      running = "events %i  " % pending_events() + running
    scr.addstr(0, scr.getmaxyx()[1] - len(running) - 1, running)

  def _update_ports(self, scr):
    """Update the ports details."""
    from .port import ports
    from .queue import attr_queue

    msg = "port count: %i" % ports()
    if len(attr_queue):
      if len(attr_queue.queue):
        msg += "; retrieving %i (of %i)" % (len(attr_queue.active),
                                      len(attr_queue.active) + len(attr_queue))
      else:
        msg += "; retrieving %i" % len(attr_queue)
    scr.addstr(self._offset, 0, msg)

    self._offset += 1

  def _update_summary(self, scr):
    """Update the summary information."""
    summary = self._stats.summary

    ports = sum((len(i) for i in summary)) - len(summary[Statistics.FAILED])
    if ports:
      msg = "%i port%s remaining: " % (ports, "s" if ports > 1 else " ")

      msgv = []
      stages = ["active", "queued", "pending", "failed"]
      for i in range(len(stages)):
        if summary[i]:
          msgv.append("%i %s" % (len(summary[i]), stages[i]))

      msg += ", ".join(msgv)

      scr.addstr(self._offset, 0, msg)

      self._offset += 1

  def _update_stage(self, scr, stage_name, stats):
    """Update various stage details."""
    if sum((len(i) for i in stats)):
      msg = "%s:%s" % (stage_name, " " * (9 - len(stage_name)))
      msgv = []
      stages = ["active", "queued", "pending", "failed"]
      for i in range(len(stages)):
        if stats[i]:
          msgv.append("%i %s" % (len(stats[i]), stages[i]))

      msg += ", ".join(msgv)
      scr.addstr(self._offset, 0, msg)
      self._offset += 1

  def _update_rows(self, scr):
    """Update the rows of port information."""
    active, queued, pending, failed = self._stats.summary
    clean = self._stats.clean

    scr.addstr(self._offset + 1, 2, ' STAGE   STATE   TIME PACKAGE')

    skip = self._skip
    lines, columns = scr.getmaxyx()
    offset = self._offset + 2
    lines -= offset
    if not self._failed_only:
      # Show at least one window of ports
      if self._idle:
        total = sum(len(i) for i in self._stats.summary)
        total += sum(len(i) for i in clean)
        if skip > total - lines:
          self._skip = skip = max(0, total - lines)
      else:
        if skip > len(active) + len(clean[0]) - lines:
          self._skip = skip = max(0, len(active) - lines)

      # Display all active ports (and time active)
      for port in active:
        if skip:
          skip -= 1
          continue
        time = port.working
        if time:
          offtime = self._stats.time - time
          time = '%3i:%02i' % (offtime / 60, offtime % 60)
        else:
          continue
        scr.addnstr(offset, 0, ' %7s  active %s %s' %
                    (STAGE_NAME[port.stage + 1], time, get_name(port)), columns)
        offset += 1
        lines -= 1
        if not lines:
          return

      # Display ports cleaning and queued to be cleaned
      for stage, cleaned in (("active", clean[0]),) + ((("queued", clean[1]),) if self._idle else ()):
        for port in cleaned:
          if skip:
            skip -= 1
            continue
          scr.addnstr(offset, 0, '   clean %7s        %s' % (stage, get_name(port)), columns)
          offset += 1
          lines -= 1
          if not lines:
            return
    elif skip > len(failed) - lines:
      # Show at least one window of ports
      self._skip = skip = max(0, len(failed) - lines)

    if self._idle or self._failed_only:
      # Show queued, pending and failed processes
      for stage, name in ((queued, "queued"), (pending, "pending"), (failed, "failed")):
        if name != "failed":
          stg = 1
          if self._failed_only:
            # Skip if showing only failed
            continue
        else:
          stg = 0
        for port in stage:
          if skip:
            skip -= 1
            continue
          stage = STAGE_NAME[port.stage + stg]
          scr.addnstr(offset, 0, ' %7s %7s        %s' %
                      (STAGE_NAME[port.stage + stg], name, get_name(port)), columns)
          offset += 1
          lines -= 1
          if not lines:
            return


class Statistics(object):
  """A collection of statistics abouts various queues, builders and ports."""

  ACTIVE  = 0
  QUEUED  = 1
  PENDING = 2
  FAILED  = 3

  def __init__(self, stages=None):
    """Collect the statistics."""
    from time import time
    from . import builder as builders
    from . import queue as queues

    self.time = time()

    self.config   = ([], [], [], [])
    self.checksum = ([], [], [], [])
    self.fetch    = ([], [], [], [])
    self.build    = ([], [], [], [])
    self.install  = ([], [], [], [])
    self.package  = ([], [], [], [])
    self.summary  = ([], [], [], [])
    self.clean = ([], [])
    self.clean[self.ACTIVE].extend(i.port for i in queues.clean_queue.active)
    self.clean[self.QUEUED].extend(i.port for i in queues.clean_queue.stalled)
    self.clean[self.QUEUED].extend(i.port for i in queues.clean_queue.queue)

    if not stages:
      stages = ("config", "checksum", "fetch", "build", "install", "package")

    seen = set()
    seen.update(self.clean[self.ACTIVE])
    seen.update(self.clean[self.QUEUED])
    for stage in stages:
      stats = getattr(self, stage)
      queue = getattr(queues, "%s_queue" % stage)
      builder = getattr(builders, "%s_builder" % stage)

      stats[self.ACTIVE].extend((i.port for i in queue.active))
      self.summary[self.ACTIVE].extend(reversed(stats[self.ACTIVE]))
      seen.update(stats[self.ACTIVE])

      stats[self.QUEUED].extend((i.port for i in queue.stalled))
      stats[self.QUEUED].extend((i.port for i in queue.queue))
      self.summary[self.QUEUED].extend(reversed(stats[self.QUEUED]))
      seen.update(stats[self.QUEUED])

      ports = list(builder.ports)
      ports.sort(key=lambda x: -x.dependant.priority)
      for port in ports:
        if port not in seen and not port.failed:
          if stage == "install" and port.stage == port.CONFIG:
            continue
          stats[self.PENDING].append(port)
      self.summary[self.PENDING].extend(reversed(stats[self.PENDING]))
      seen.update(stats[self.PENDING])

      for port in builder.failed:
        if port not in seen:
          if port.failed:
            stats[self.FAILED].append(port)
          else:
            seen.add(port)
      self.summary[self.FAILED].extend(reversed(stats[self.FAILED]))
      seen.update(stats[self.FAILED])

    for i in self.summary:
      i.reverse()