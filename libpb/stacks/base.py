"""
The stacks.base module.  This module contains the basic Stack and Stage classes.
"""

import abc
import time

from libpb import event, job, log

__all__ = ["Stack", "Stage"]


class Stack(object):
    """The Stack class, each stack is a distinct series of stages."""
    def __init__(self, name):
        self.failed = False
        self.name = name
        self.working = False


class Stage(job.Job):
    """The Stage class, handles separations of work for a port."""
    __metaclass__ = abc.ABCMeta

    name = ""
    prev = None
    stack = None

    def __init__(self, port, load=1):
        super(Stage, self).__init__(load, None)
        self.port = port
        self.pid = None
        self.stack = port.stacks[self.stack]
        self.failed = self.stack.failed

    def __str__(self):
        return self.name

    @abc.abstractmethod
    def _do_stage(self):
        """Execute commands required to complete this stage."""
        pass

    @staticmethod
    def check(port):  # pylint: disable-msg=W0613
        """Check if it is possible to complete this stage."""
        # NB: checks must be quick and invariant
        return True

    def complete(self):  # pylint: disable-msg=R0201
        """Indicate if the port has already completed this stage."""
        return False

    @property
    def priority(self):  # pylint: disable-msg=E0202
        """The priority of the job, inherited from the port's priority."""
        return self.port.priority

    def __le__(self, other):
        return self.port < other.port

    def work(self):
        assert self.prev in self.port.stages
        assert not self.stack.working
        assert not self.failed
        assert self.check(self.port)
        assert (not self.port.dependency or
                not self.port.dependency.check(self.__class__))

        log.debug("Stage.work()", "Port '%s': starting stage %s" %
                      (self.port.origin, self.name))
        if self.complete():
            # Cannot call self._finalise(True) directly as self.done() cannot
            # be called from within the scope of self.work()
            event.post_event(self._finalise, True)
        else:
            self._do_stage()  # May throw job.JobStalled()
            self.stack.working = time.time()

    def _finalise(self, status):
        """Finalise the stage."""
        if not status:
            log.error("Stage._finalise()", "Port '%s': failed stage %s" %
                          (self.port.origin, self.name))
            if self.stack.name == "common":
                for stack in self.port.stacks.values():
                    stack.failed = self.__class__
            else:
                self.stack.failed = self.__class__
            self.failed = True
        else:
            log.debug("Stage._finalise()", "Port '%s': finished stage %s" %
                          (self.port.origin, self.name))
        self.stack.working = False
        self.port.stages.add(self.__class__)
        self.done()
