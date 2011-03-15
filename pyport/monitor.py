"""Displays about activity."""

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


STAGE_NAME = ["config", "config", "chcksm", "fetch", "build", "instal", "error"]

def get_name(port):
  """Get the ports name."""
  return '%s (%s)' % (port.origin, port.attr['pkgname'].rsplit('-', 1)[1])

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

  def run(self):
    """Refresh the display."""
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
    from curses import KEY_CLEAR, ascii

    run = False
    while True:
      ch = self._stdscr.getch()
      if ch == -1:
        break
      elif ch == ord('f'):
        self._failed_only = not self._failed_only
      elif ch == ord('i') or ch == ord('I'):
        self._idle = not self._idle
      elif ch == ord('q'):
        exit()
      elif ch == KEY_CLEAR or ch == ascii.FF:
        self._stdscr.clear()
      else:
        continue
      run = True
    if run:
      self.run()

  def _update_header(self, scr):
    """Update the header details."""
    from time import strftime

    self._offset = 0
    self._update_ports(scr)
    self._update_summary(scr)
    self._update_stage(scr, "Checksum", self._stats.checksum)
    self._update_stage(scr, "Fetch", self._stats.fetch)
    self._update_stage(scr, "Build", self._stats.build)
    self._update_stage(scr, "Install", self._stats.install)

    offset = self._stats.time - self._time
    secs, mins, hours = offset % 60, offset / 60 % 60, offset / 60 / 60 % 60
    days = offset / 60 / 60 / 24
    running = "running %i+%02i:%02i:%02i  " % (days, hours, mins, secs)
    running += strftime("%H:%M:%S")
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

    scr.addstr(self._offset + 1, 2, 'STAGE   STATE   TIME PORT (VERSION)')

    lines, columns = scr.getmaxyx()
    offset = self._offset + 2
    lines -= offset
    if not self._failed_only:
      for port in active:
        time = port.working
        if time:
          offtime = self._stats.time - time
          time = '%3i:%02i' % (offtime / 60, offtime % 60)
        else:
          continue
        scr.addnstr(offset, 0, ' %6s  active %s %s' %
                    (STAGE_NAME[port.stage + 1], time, get_name(port)), columns)
        offset += 1
        lines -= 1
        if not lines:
          return

    if self._idle or self._failed_only:
      for stage, name in ((queued, "queued"), (pending, "pending"), (failed, "failed")):
        if self._failed_only and name != "failed":
          continue
        for port in stage:
          scr.addnstr(offset, 0, ' %6s  %6s        %s' %
                      (STAGE_NAME[port.stage + 1], name, get_name(port)), columns)
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

  def __init__(self):
    """Collect the statistics."""
    from time import time
    from . import builder as builders
    from . import queue as queues

    self.config   = ([], [], [], [])
    self.checksum = ([], [], [], [])
    self.fetch    = ([], [], [], [])
    self.build    = ([], [], [], [])
    self.install  = ([], [], [], [])
    self.summary  = ([], [], [], [])

    self.time = time()

    seen = set()
    for stage in ("config", "checksum", "fetch", "build", "install"):
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

      for port in builder.ports:
        if port not in seen:
          stats[self.PENDING].append(port)
      self.summary[self.PENDING].extend(reversed(stats[self.PENDING]))
      seen.update(stats[self.PENDING])

      for port in builder.failed:
        if port not in seen:
          stats[self.FAILED].append(port)
      self.summary[self.FAILED].extend(reversed(stats[self.FAILED]))
      seen.update(stats[self.FAILED])

    for i in self.summary:
      i.reverse()
