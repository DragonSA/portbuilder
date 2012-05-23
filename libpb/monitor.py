"""Displays about activity."""

from __future__ import absolute_import

import abc
import collections
import curses, curses.ascii
import sys
import time

from libpb import env, event, queue, stacks

from .port.port import Port
from .builder import Builder

__all__ = ["Monitor", "Top"]


class Monitor(object):
    """The monitor abstract super class."""

    __metaclass__ = abc.ABCMeta

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

    @abc.abstractmethod
    def run(self):
        """Refresh the display."""
        pass

    def _init(self):
        """Run any initialisation required."""
        pass

    def _deinit(self):
        """Run any denitialisation required."""
        pass

STAGES = (
    stacks.Depend,
    stacks.Checksum,
    stacks.Fetch,
    stacks.Build,
    stacks.Install,
    stacks.PkgInstall,
    stacks.RepoInstall,
    stacks.Package,
  )

STATUS = collections.OrderedDict((
    (Builder.ACTIVE, "active"),
    (Builder.QUEUED, "queued"),
    (Builder.ADDED,  "pending"),
    (Builder.FAILED, "failed"),
    (Builder.DONE,   "done"),
  ))


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
        self._indirect = False
        self._idle = True
        self._skip = 0
        self._quit = 0

        self._last_event_count = 0

    def run(self):
        """Refresh the display."""
        from . import state

        state.sort()
        if env.flags["fetch_only"]:
            stages = tuple(state[i] for i in STAGES[:3])
        else:
            stages = tuple(state[i] for i in STAGES)
        self._curr_time = time.time()
        self._stdscr.erase()
        self._update_header(self._stdscr, stages)
        self._update_rows(self._stdscr, stages)
        self._stdscr.move(self._offset, 0)
        self._stdscr.refresh()

    def _init(self):
        """Initialise the curses library."""
        self._stdscr = curses.initscr()
        self._stdscr.keypad(1)
        self._stdscr.nodelay(1)
        self._stdscr.clear()
        curses.cbreak()
        curses.noecho()

        event.event(sys.stdin).connect(self._userinput)

    def _deinit(self):
        """Shutdown the curses library."""
        self._stdscr.move(self._stdscr.getmaxyx()[0] - 1, 0)
        self._stdscr.clrtoeol()
        self._stdscr.refresh()

        self._stdscr.keypad(0)
        curses.nocbreak()
        curses.echo()
        curses.endwin()

        event.event(sys.stdin, clear=True)

    def _userinput(self):
        """Get user input and change display options."""
        run = False
        while True:
            char = self._stdscr.getch()
            if char == -1:
                break
            elif char == ord('d'):
                # Toggle showing indirect failures
                self._indirect = not self._indirect
            elif char == ord('f'):
                # Toggle fetch only display
                self._failed_only = not self._failed_only
            elif char == ord('i'):
                # Toggle showing idle
                self._idle = not self._idle
            elif char == ord('q'):
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
            elif char == curses.KEY_CLEAR or char == curses.ascii.FF:
                # Redraw window
                self._stdscr.clear()
            elif char == curses.KEY_PPAGE:
                # Page up display
                self._skip -= self._stdscr.getmaxyx()[0] - self._offset - 2
                self._skip = max(0, self._skip)
            elif char == curses.KEY_NPAGE:
                # Page down display
                self._skip += self._stdscr.getmaxyx()[0] - self._offset - 2
            else:
                # Unknown input
                continue
            run = True
        if run:
            # Redraw display if required
            self.run()

    def _update_header(self, scr, stages):
        """Update the header details."""
        self._offset = 0
        self._update_ports(scr)
        self._update_summary(scr, stages)
        for stage in stages:
            self._update_stage(scr, stage)

        offset = self._curr_time - self._time
        secs, mins, hours = offset % 60, offset / 60 % 60, offset / 60 / 60 % 60
        days = offset / 60 / 60 / 24
        # Display running time
        running = "running %i+%02i:%02i:%02i  " % (days, hours, mins, secs)
        # Display current time
        running += time.strftime("%H:%M:%S")
        events, self._last_event_count = self._last_event_count, event.event_count()
        events = self._last_event_count - events - 1
        if events > 0:
            # Display pending events
            running = "event%s %i  " % ("s" if events > 1 else "", events) + running
        scr.addstr(0, scr.getmaxyx()[1] - len(running) - 1, running)

    def _update_ports(self, scr):
        """Update the ports details."""
        from .port import ports

        msg = "port count: %i" % ports()
        if len(queue.attr):
            if len(queue.attr.queue):
                msg += "; retrieving %i (of %i)" % (len(queue.attr.active),
                                                    len(queue.attr.active) +
                                                    len(queue.attr))
            else:
                msg += "; retrieving %i" % len(queue.attr)
        scr.addstr(self._offset, 0, msg)

        self._offset += 1

    def _update_summary(self, scr, stages):
        """Update the summary information."""
        msg = dict((i, 0) for i in STATUS.values())
        ports = 0
        for stage in stages:
            for stat, status in STATUS.items():
                msg[status] += len(stage[stat])
                if stat not in (Builder.FAILED, Builder.DONE):
                    ports += len(stage[stat])
                if stat == Builder.FAILED and not self._indirect:
                    msg[status] -= len([i for i in stage[stat] if "failed" not in i.flags])

        msg = ", ".join("%i %s" % (msg[i], i) for i in STATUS.values() if msg[i])
        scr.addstr(
                self._offset, 0, "%i port%s remaining: %s" %
                (ports, " " if ports == 1 else "s", msg))
        self._offset += 1
        self._skip = min(self._skip, ports - 1)

    def _update_stage(self, scr, stage):
        """Update various stage details."""
        msg = []
        for state, status in STATUS.items()[:-1]:
            if stage.status[state]:
                length = len(stage[state])
                if state == Builder.FAILED and not self._indirect:
                    length -= len([i for i in stage[state] if "failed" not in i.flags])
                    if not length:
                        continue
                msg.append("%i %s" % (length, status))

        if msg:
            stage_name = stage.stage.name
            scr.addstr(
                    self._offset, 0, "%s:%s%s" %
                    (stage_name, " " * (9 - len(stage_name)), ", ".join(msg)))
            self._offset += 1

    def _update_rows(self, scr, stages):
        """Update the rows of port information."""
        scr.addstr(self._offset + 1, 2, ' STAGE   STATE   TIME PACKAGE')

        def ports(stages, status):
            """Retrieve all the ports at status from stages."""
            for stage in reversed(stages):
                stat = stage[status]
                if self._skip:
                    length = len(stat)
                    if status == Builder.FAILED and not self._indirect:
                        length -= len([i for i in stat if "failed" not in i.flags])
                    if self._skip >= length:
                        self._skip -= length
                        continue
                    else:
                        stat = stat[self._skip:]
                        self._skip = 0
                for port in stat:
                    if (status == Builder.FAILED and not self._indirect and
                        "failed" not in port.flags):
                        continue
                    yield port, stage.stage

        skip = self._skip
        lines, columns = scr.getmaxyx()
        offset = self._offset + 2
        lines -= offset
        if self._failed_only:
            status = (Builder.FAILED,)
        elif self._idle:
            status = tuple(i for i in STATUS)
        else:
            status = (Builder.ACTIVE,)

        if Builder.ACTIVE == status[0]:
            status = status[1:]
            for port, stage in ports(stages, Builder.ACTIVE):
                if not port.stacks[stage.stack].working:
                    continue

                offtime = self._curr_time - port.stacks[stage.stack].working
                active = '%3i:%02i' % (offtime / 60, offtime % 60)
                scr.addnstr(
                        offset, 0, ' %7s  active %s %s' %
                        (stage.name[:6].lower(), active, get_name(port)),
                        columns)
                offset += 1
                lines -= 1
                if not lines:
                    self._skip = skip
                    return

            # Display ports cleaning and queued to be cleaned
            if self._idle:
                clean = (queue.clean.active + queue.clean.stalled +
                         queue.clean.queue)
            else:
                clean = queue.clean.active
            if self._skip >= len(clean):
                self._skip -= len(clean)
            else:
                for job in clean[self._skip:]:
                    # TODO: Currently clean jobs don't show progress
                    if False and job.port.working:
                        offtime = self._curr_time - job.port.working
                        active = '%3i:%02i' % (offtime / 60, offtime % 60)
                        state = "active"
                    else:
                        active = ' ' * 6
                        state = "queued"
                    scr.addnstr(
                            offset, 0, '   clean  %s %s %s' %
                            (state, active, get_name(job.port)), columns)
                    offset += 1
                    lines -= 1
                    if not lines:
                        self._skip = skip
                        return
                self._skip = 0

        for status in status:
            for port, stage in ports(stages, status):
                scr.addnstr(
                        offset, 0, ' %7s %7s        %s' %
                        (stage.name[:6].lower(), STATUS[status],
                         get_name(port)), columns)
                offset += 1
                lines -= 1
                if not lines:
                    self._skip = skip
                    return

        # make sure at least one port is visible
        if self._skip:
            self._skip = max(0, skip - self._skip - 1)
            self._update_rows(scr, stages)
        else:
            self._skip = skip
