"""
The exit module.  This module handles the termination of the ports framework.
In addition, it also checks for idleness and terminates the program when it
occures
"""

class AutoExit(object):
  """
      Check if the queues are busy.  If all are idle terminate the program.
      Also handle terminating the program, including cleaning up of left over
      ports.
  """

  def __init__(self, timeout, pause):
    """
       Create the exit handlers.  The shutdown handler is registered and
       various signal handlers.

       @param timeout: How often to check for a stall
       @type timeout: C{float}
       @param pause: How often to check for a terminate request
       @type pause: C{float}
    """
    from atexit import register
    from os import getpid, setpgrp
    from signal import signal, SIGINT, SIGTERM
    self.__start = False
    self.__pause = pause
    self.__timeout = timeout
    self.__term = False
    self.__pid = getpid()

    setpgrp()
    register(self.terminate)
    # Make pylint happier(otherwise sig_handler has an unused parameter 'frame')
    sig_handler = lambda x, y: self.sig_handler(x)
    signal(SIGINT, sig_handler)
    signal(SIGTERM, sig_handler)

  def timeout(self, timeout):
    """
       Set the timeout value.

       @param timeout: How often to check for a stall
       @type timeout: C{float}
    """
    self.__timeout = timeout

  def pause(self, pause):
    """
       Set a pause value.

       @param pause: How often to check for a terminate request
       @type pause: C{float}
    """
    self.__pause = pause

  def sig_handler(self, sig):
    """
       Signal handler, initiates a terminate request

       @param sig: The signal received
       @type sig: C{int}
    """
    from os import getpid, kill
    from signal import signal, SIGINT, SIGTERM, SIG_DFL

    signal(SIGINT, SIG_DFL)
    signal(SIGTERM, SIG_DFL)
    if self.__pid != getpid():
      kill(self.__pid, sig)
      kill(getpid(), sig)
    else:
      terminate()

  def start(self):
    """
       Tell the idle checker to start checking for idleness
    """
    self.__start = True

  def terminate(self):
    """
      Shutdown the program properly.
    """
    from os import killpg
    from queue import queues
    from signal import SIGTERM

    # Kill all running processes (they should clean themselves up)
    if not self.__term:
      self.__term = True
      for i in queues:
        i.terminate()
      killpg(0, SIGTERM)

  def run(self):
    """
       Execute the main handlers.  This needs to be run from the main loop to
       allow signals to be processed promptly.
    """
    from port import port_cache, Port
    from queue import queues
    from time import sleep

    while True:
      try:
        count = 0
        cycles = int(self.__timeout / self.__pause)
        while (count < cycles or not self.__start) and not self.__term:
          sleep(self.__pause)
          count += 1

        # If a queue is busy then don't terminate
        term = True
        for i in queues:
          if len(i):
            term = False
            break

        if term or self.__term:
          if not self.__term:
            terminate()

          # Wait for everyone to finish
          for i in queues:
            i.join()

          # Cleanup all ports that have built but not installed
          for i in port_cache.itervalues():
            if i and not i.failed() and (i.stage() == Port.BUILD or \
                (i.stage() == Port.INSTALL and i.working())):
              i.clean()
          exit(self.__term and 0 or 1)
      except KeyboardInterrupt:
        self.terminate()

exit_handler = AutoExit(0.1, 0.01)  #: Exit handler
#: Alias for common functions of exit_handler
terminate = exit_handler.terminate
