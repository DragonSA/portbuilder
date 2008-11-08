"""
The exit module.  This module handles the termination of the ports framework.
In addition, it also checks for idleness and terminates the program when it
occures
"""
from __future__ import absolute_import, with_statement

__all__ = ['set_timeout', 'start', 'terminate']

class AutoExit(object):
  """
      Check if the queues are busy.  If all are idle terminate the program.
      Also handle terminating the program, including cleaning up of left over
      ports.
  """

  def __init__(self, timeout):
    """
       Create the exit handlers.  The shutdown handler is registered and
       various signal handlers.

       @param timeout: How often to check for a stall
       @type timeout: C{float}
    """
    from atexit import register
    from logging import getLogger
    from os import getpid, setpgrp
    from signal import signal, SIGINT, SIGTERM
    from threading import Condition, Lock

    self._log = getLogger('pypkg.AutoExit')
    self.__lock = Lock()
    self.__wait = Condition(self.__lock)
    self.__pid = getpid()
    self.__started = False
    self.__timeout = timeout
    self.__term = False

    self.__lock.acquire()
    setpgrp()
    register(self.terminate)
    # Make pylint happier(otherwise sig_handler has an unused parameter 'frame')
    sig_handler = lambda x, y: self.sig_handler(x)
    signal(SIGINT, sig_handler)
    signal(SIGTERM, sig_handler)

  def set_timeout(self, timeout):
    """
       Set the timeout value.

       @param timeout: How often to check for a stall
       @type timeout: C{float}
    """
    self.__timeout = timeout

  def sig_handler(self, sig):
    """
       Signal handler, initiates a terminate request

       @param sig: The signal received
       @type sig: C{int}
    """
    from os import getpid, kill
    from signal import signal, SIGINT, SIGTERM, SIG_DFL

    if self.__pid != getpid():
      signal(SIGINT, SIG_DFL)
      signal(SIGTERM, SIG_DFL)
      kill(self.__pid, sig)
      kill(getpid(), sig)
    else:
      self._log.info("Sig Handler initiated, most of the following (and some " \
                "previous) messages are a result of this and can be safely " \
                "ignored")
      terminate()

  def start(self):
    """
       Start the idle monitor.
    """
    with self.__lock:
      assert not self.__started
      self.__started = True
      self.__wait.notify()

  def terminate(self):
    """
       Shutdown the program properly.
    """
    if not self.__term:
      self.__term = True
      with self.__lock:
        self.__wait.notify()

  def run(self):
    """
       Execute the main handlers.  This needs to be run from the main loop to
       allow signals to be processed promptly.
    """
    from os import killpg
    from signal import signal, SIGINT, SIGTERM, SIG_IGN
    
    from pypkg.port import cache, Port
    from pypkg.queue import queues
    from pypkg import monitor

    # Wait for the start signal (could be triggered via terminate or start)
    self.__wait.wait()

    try:
      while not self.__term:
        if self.__wait.wait(self.__timeout):
          break

        # If a queue is busy then don't terminate
        term = True
        for i in queues[:-1]:
          if len(i):
            term = False
            break

        if term:
          self._log.info("No queues active, terminating")
          self.__lock.release()
          self.terminate()
    except KeyboardInterrupt:
      if self.__lock.locked():
        self.__lock.release()
      self.terminate()

    self._log.info("Initiating terminate sequance")

    # Switching off sig handling.  This is the end
    signal(SIGINT, SIG_IGN)
    signal(SIGTERM, SIG_IGN)

    # Terminating all queues
    for i in queues:
      i.terminate()

    # Killing all spawned processes
    killpg(0, SIGTERM)
    
    # Wait for everyone to finish
    for i in queues:
      i.join()

    # Cleanup all ports that have built but not installed
    for i in cache.itervalues():
      if i and not i.failed() and (i.stage() == Port.BUILD or \
          (i.stage() == Port.INSTALL and i.working())):
        i.clean()

    monitor.monitor.stop()
    exit(0)


exit_handler = AutoExit(0.1)  #: Exit handler
set_timeout = exit_handler.set_timeout
start = exit_handler.start
terminate = exit_handler.terminate
