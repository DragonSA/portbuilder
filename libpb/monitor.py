"""Displays about activity."""

from __future__ import absolute_import

from abc import ABCMeta, abstractmethod
import curses, curses.ascii
import sys
import time

from .port.port import Port
from .builder import Builder

__all__ = ["Monitor", "Top"]


class Monitor(object):
    """The monitor abstract super class."""

    __metaclass__ = ABCMeta

    def __init__(self):
        """Initialise the monitor"""
        from .event import alarm, event, stop, start

        self.delay = 1  #: Delay between monitor iterations
        self._running = False  #: Indicate if we have started
        self._timer_id = alarm()

        event(self._timer_id, "t", data=self.delay).connect(self.alarm)
        start.connect(self.start)
        stop.connect(self.stop)

    def alarm(self):
        """Monitor interface for event manager."""
        if self._running:
            self.run()

    def start(self):
        """Start the monitor."""
        if not self._running:
            self._running = True
            self._init()
            self.run()

    def stop(self):
        """Stop the monitor."""
        if self._running:
            self.run()
            self._running = False
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


STAGE_NAME = ("config", "config", "depend", "chcksm", "fetch", "build",
              "install", "package", "pkginst", "error")
STAGE = (
    (Port.CHECKSUM,   "Checksum"),
    (Port.DEPEND,     "Depend"),
    (Port.FETCH,      "Fetch"),
    (Port.BUILD,      "Build"),
    (Port.INSTALL,    "Install"),
    (Port.PKGINSTALL, "Pkginst"),
    (Port.PACKAGE,    "Package"),
  )

STATUS_NAME = ("pending", "queued", "active", "failed", None, "done")
STATUS = (
    (Builder.ACTIVE, "active"),
    (Builder.QUEUED, "queued"),
    (Builder.ADDED,  "pending"),
    (Builder.FAILED, "failed"),
    (Builder.DONE,   "done"),
  )


def get_name(port):
    """Get the ports name."""
    return port.attr["pkgname"]


class Top(Monitor):
    """A monitor modelled after the top(1) utility."""

    def __init__(self):
        """Initialise the top monitor."""
        Monitor.__init__(self)

        self._offset = 0
        self._time = time.time()
        self._curr_time = self._time
        self._stdscr = None
        self._stats = None

        self._failed_only = False
        self._idle = True
        self._skip = 0
        self._quit = 0

        self._last_event_count = 0

    def run(self):
        """Refresh the display."""
        self._curr_time = time.time()
        self._stdscr.erase()
        self._update_header(self._stdscr)
        self._update_rows(self._stdscr)
        self._stdscr.move(self._offset, 0)
        self._stdscr.refresh()

    def _init(self):
        """Initialise the curses library."""
        from .event import event

        self._stdscr = curses.initscr()
        self._stdscr.keypad(1)
        self._stdscr.nodelay(1)
        self._stdscr.clear()
        curses.cbreak()
        curses.noecho()

        event(sys.stdin).connect(self._userinput)

    def _deinit(self):
        """Shutdown the curses library."""
        from .event import event

        self._stdscr.move(self._stdscr.getmaxyx()[0] - 1, 0)
        self._stdscr.clrtoeol()
        self._stdscr.refresh()

        self._stdscr.keypad(0)
        curses.nocbreak()
        curses.echo()
        curses.endwin()

        event(sys.stdin, clear=True)

    def _userinput(self):
        """Get user input and change display options."""
        run = False
        while True:
            ch = self._stdscr.getch()
            if ch == -1:
                break
            elif ch == ord('f'):
                # Toggle fetch only display
                self._failed_only = not self._failed_only
            elif ch == ord('i') or ch == ord('I'):
                # Toggle showing idle
                self._idle = not self._idle
            elif ch == ord('q'):
                # Quit
                from . import stop

                self._quit += 1
                if self._quit == 1:
                    stop()
                elif self._quit == 2:
                    stop(kill=True)
                elif self._quit == 3:
                    stop(kill=True, kill_clean=True)
                    raise SystemExit(254)
                continue
            elif ch == curses.KEY_CLEAR or ch == curses.ascii.FF:
                # Redraw window
                self._stdscr.clear()
            elif ch == curses.KEY_PPAGE:
                # Page up display
                self._skip -= self._stdscr.getmaxyx()[0] - self._offset - 2
                self._skip = max(0, self._skip)
            elif ch == curses.KEY_NPAGE:
                # Page down display
                self._skip += self._stdscr.getmaxyx()[0] - self._offset - 2
            else:
                # Unknown input
                continue
            run = True
        if run:
            # Redraw display if required
            self.run()

    def _update_header(self, scr):
        """Update the header details."""
        from .event import event_count
        from . import state

        self._offset = 0
        self._update_ports(scr)
        self._update_summary(scr)
        for stage, stgname in STAGE:
            self._update_stage(scr, stgname, state[stage])

        offset = self._curr_time - self._time
        secs, mins, hours = offset % 60, offset / 60 % 60, offset / 60 / 60 % 60
        days = offset / 60 / 60 / 24
        # Display running time
        running = "running %i+%02i:%02i:%02i  " % (days, hours, mins, secs)
        # Display current time
        running += time.strftime("%H:%M:%S")
        events, self._last_event_count = self._last_event_count, event_count()
        events = self._last_event_count - events - 1
        if events > 0:
            # Display pending events
            running = "events %i  " % events + running
        scr.addstr(0, scr.getmaxyx()[1] - len(running) - 1, running)

    def _update_ports(self, scr):
        """Update the ports details."""
        from .port import ports
        from .queue import attr_queue

        msg = "port count: %i" % ports()
        if len(attr_queue):
            if len(attr_queue.queue):
                msg += "; retrieving %i (of %i)" % (len(attr_queue.active),
                                                    len(attr_queue.active) +
                                                    len(attr_queue))
            else:
                msg += "; retrieving %i" % len(attr_queue)
        scr.addstr(self._offset, 0, msg)

        self._offset += 1

    def _update_summary(self, scr):
        """Update the summary information."""
        from . import state

        msg = dict((status[1], 0) for status in STATUS)
        ports = 0
        for stage in state.stages:
            for stat, status in STATUS:
                msg[status] += len(stage[stat])
                ports += len(stage[stat])

        if ports:
            msg = ", ".join("%i %s" % (msg[status[1]], status[1])
                            for status in STATUS if msg[status[1]])
            scr.addstr(
                    self._offset, 0, "%i port%s remaining: %s" %
                    (ports, "s" if ports > 1 else " ", msg))
            self._offset += 1
        self._skip = min(self._skip, ports - 1)

    def _update_stage(self, scr, stage_name, stats):
        """Update various stage details."""
        msg = []
        for stat, status in STATUS[:1]:
            if stats.status[stat]:
                msg.append("%i %s" % (len(stats[stat]), status))

        if msg:
            scr.addstr(
                    self._offset, 0, "%s:%s%s" %
                    (stage_name, " " * (9 - len(stage_name)), ", ".join(msg)))
            self._offset += 1

    def _update_rows(self, scr):
        """Update the rows of port information."""
        from .env import flags
        from .queue import clean_queue
        from . import state

        scr.addstr(self._offset + 1, 2, ' STAGE   STATE   TIME PACKAGE')

        def ports(stages, status):
            """Retrieve all the ports at status from stages."""
            for stage in reversed(stages):
                stat = stage[status]
                if self._skip:
                    if self._skip >= len(stat):
                        self._skip -= len(stat)
                        continue
                    else:
                        stat = stat[self._skip:]
                        self._skip = 0
                for port in stat:
                    yield port

        skip = self._skip
        lines, columns = scr.getmaxyx()
        offset = self._offset + 2
        lines -= offset
        state.sort()
        if flags["fetch_only"]:
            stages = state[:Port.FETCH+1]
        else:
            stages = state.stages
        if self._failed_only:
            status = (Builder.FAILED)
        elif self._idle:
            status = tuple(status[0] for status in STATUS)
        else:
            status = (Builder.ACTIVE)

        if Builder.ACTIVE == status[0]:
            status = status[1:]
            for port in ports(stages, Builder.ACTIVE):
                if not port.working:
                    continue

                offtime = self._curr_time - port.working
                active = '%3i:%02i' % (offtime / 60, offtime % 60)
                scr.addnstr(
                        offset, 0, ' %7s  active %s %s' %
                        (STAGE_NAME[port.stage + 1], active, get_name(port)),
                        columns)
                offset += 1
                lines -= 1
                if not lines:
                    self._skip = skip
                    return

            # Display ports cleaning and queued to be cleaned
            if self._idle:
                clean = (clean_queue.active + clean_queue.stalled +
                         clean_queue.queue)
            else:
                clean = clean_queue.active
            if self._skip >= len(clean):
                self._skip -= len(clean)
            else:
                for job in clean[self._skip:]:
                    if job.port.working:
                        offtime = self._curr_time - job.port.working
                        active = '%3i:%02i' % (offtime / 60, offtime % 60)
                    else:
                        active = ' ' * 6
                    scr.addnstr(
                            offset, 0, '   clean  active %s %s' %
                            (active, get_name(job.port)), columns)
                    offset += 1
                    lines -= 1
                    if not lines:
                        self._skip = skip
                        return
                self._skip = 0

        for status in status:
            stg = 0 if status in (Builder.FAILED, Builder.DONE) else 1
            for port in ports(stages, status):
                scr.addnstr(
                        offset, 0, ' %7s %7s        %s' %
                        (STAGE_NAME[port.stage + stg], STATUS_NAME[status],
                         get_name(port)), columns)
                offset += 1
                lines -= 1
                if not lines:
                    self._skip = skip
                    return

        # make sure at least one port is visible
        if self._skip:
            self._skip = max(0, skip - self._skip - 1)
            self._update_rows(scr)
        else:
            self._skip = skip
