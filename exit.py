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

  def __init__(self, timeout):
    """
       Create the exit handlers.  The shutdown handler is registered and
       various signal handlers.

       @param timeout: How often to check for a stall
       @type timeout: C{float}
    """
    from atexit import register
    from os import getpid, setpgrp
    from signal import signal, SIGINT, SIGTERM
    from threading import Condition, Lock
    
    self.__wait = Condition(Lock())
    self.__pid = getpid()
    self.__timeout = timeout
    self.__term = False

    self.__wait.acquire()
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
    from signal import signal, SIGINT, SIGTERM, SIG_DFL, SIG_IGN

    if self.__pid != getpid():
      signal(SIGINT, SIG_DFL)
      signal(SIGTERM, SIG_DFL)
      kill(self.__pid, sig)
      kill(getpid(), sig)
    else:
      from logging import getLogger
      signal(SIGINT, SIG_IGN)
      signal(SIGTERM, SIG_IGN)
      getLogger('pypkg.AutoExit').info("Sig Handler initiated, most of the " \
                "following (and some previous) messages are a result of this " \
                "and can be safely ignored")
      terminate()

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
      self.__wait.notify()

  def run(self):
    """
       Execute the main handlers.  This needs to be run from the main loop to
       allow signals to be processed promptly.
    """
    from monitor import monitor
    from port import cache, Port
    from queue import queues

    try:
      while self.__term:
        if self.__wait.wait(self.__timeout):
          break
        
        # If a queue is busy then don't terminate
        term = True
        for i in queues:
          if len(i):
            term = False
            break

        if term:
          self.terminate()
    except KeyboardInterrupt:
      self.terminate()

    # Wait for everyone to finish
    for i in queues:
      i.join()

    # Cleanup all ports that have built but not installed
    for i in cache.itervalues():
      if i and not i.failed() and (i.stage() == Port.BUILD or \
          (i.stage() == Port.INSTALL and i.working())):
        i.clean()

    monitor.stop()
    exit(0)
    

exit_handler = AutoExit(0.1)  #: Exit handler
#: Alias for common functions of exit_handler
terminate = exit_handler.terminate
