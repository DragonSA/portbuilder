"""
The Tools module.  This module contains various utilities (that should be in
the standard libraries) for ease of programming...
"""

from contextlib import contextmanager
from threading import Thread

@contextmanager
def invert(thing):
  """
     Invert the order applied to an object.

     @param thing: The object to invert
  """
  thing.__exit__(None, None, None)
  yield thing
  thing.__enter__()

def recurse_depends(port):
  """
     Returns a list of all the dependancies of the given port.

     @param port: The port with which to get the dependancies
     @type port: C{port}
     @return: The complete list of dependancies
     @rtype: C{[Port]}
  """
  depends = set()
  new = set((port.depends(),))
  while len(new):
    depends.update(new)
    new = set([[j for j in i.dependancies()] for i in new], [])
    new = new.difference(depends)
  return [i.port() for i in depends]

def terminate():
  """
     Shutdown the program properly.
  """
  exit_handler.start()
  exit_handler.terminate()

def auto_exit(timeout=5):
  """
     This function checks if the system is busy [via the queues] and terminates
     the program if they are not busy.  Should never happen, but...

     @param timeout: How often to check for idleness
     @type timeout: C{int}
     @return: The thread handling idle checking
     @rtype: C{Thread}
  """
  exit_handler.timeout(timeout)
  exit_handler.start()

class AutoExit(Thread):
  """
      Check if the queues are busy.  If all are idle terminate the program.
  """

  def __init__(self, timeout, pause):
    from atexit import register
    from os import getpid, setpgrp
    from signal import signal, SIGINT, SIGTERM
    Thread.__init__(self)
    self.__created = False
    self.__pause = pause
    self.__timeout = timeout
    self.__term = False
    self.__pid = getpid()

    setpgrp()
    register(terminate)
    signal(SIGINT, lambda x, y: self.terminate())
    signal(SIGTERM, lambda x, y: self.terminate())

  def timeout(self, timeout):
    self.__timeout = timeout

  def pause(self, pause):
    self.__pause = pause

  def start(self):
    if not self.__created:
      self.__created = True
      #self.setDaemon(True)
      Thread.start(self)
      # TODO, make proper handler, even if pid is different...

  def int_handler(self, sig, frame):
    from os import getpid, kill
    from signal import signal, SIGINT, SIGTERM, SIG_DFL

    signal(SIGINT, SIG_DFL)
    signal(SIGTERM, SIG_DFL)
    if self.__pid != getpid():
      print "Wrong pid"
      kill(self.__pid, sig)
      kill(getpid(), sig)
    else:
      print "Right pid"
      terminate()

  def terminate(self):
    """
      Shutdown the program properly.
    """
    from os import killpg
    from queue import queues
    from signal import SIGTERM

    # Kill all running processes (they should clean themselves up)
    print "RUNNING TERMINATE...", self.__term
    if not self.__term:
      for i in queues:
        i.terminate()
        assert i.pool() == 0
      killpg(0, SIGTERM)
      self.__term = True

  def run(self):
    from os import _exit
    from port import ports, Port
    from queue import queues
    from time import sleep

    self.__created = True

    while True:
      try:
        count = 0
        cycles = int(self.__timeout / self.__pause)
        while count < cycles and not self.__term:
          sleep(self.__pause)
          count += 1
        print "auto_handler cycle"

        # If a queue is busy then don't terminate
        term = True
        for i in queues:
          if len(i):
            term = False
            break

        if term or self.__term:
          print "calling exit(0)"
          if not self.__term:
            terminate()

          # Wait for everyone to finish
          for i in queues:
            #print i.pool(), len(i)
            i.join()

          print "all queues idle"
          # Cleanup all ports that have built but not installed
          for i in ports.itervalues():
            if i and not i.failed() and (i.stage() == Port.BUILD or \
                (i.stage() == Port.INSTALL and i.working())):
              i.clean()
          print "all ports clean"
          _exit(self.__term and 0 or 1)
      except KeyboardInterrupt:
        self.terminate()

exit_handler = AutoExit(5, 0.1)
