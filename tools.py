"""
The Tools module.  This module contains various utilities (that should be in
the standard libraries) for ease of programming...
"""

from contextlib import contextmanager

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
    self.__created = False
    self.__pause = pause
    self.__timeout = timeout
    self.__term = False
    self.__pid = getpid()

    setpgrp()
    register(terminate)
    signal(SIGINT, self.sig_handler)
    signal(SIGTERM, self.sig_handler)

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

  def sig_handler(self, sig, frame):
    """
       Signal handler, initiates a terminate request

       @param sig: The signal received
       @type sig: C{int}
       @param frame: The frame interrupted
       @type frame: C{Frame}
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

exit_handler = AutoExit(0.1, 0.01)  #: Exit handler
#: Alias for common functions of exit_handler
terminate = exit_handler.terminate

def run_main(main):
  """
     Run the main function in its own thread and then runs the exit handler
     function.  This function does not return.

     @param main: The main function to execute
     @type main: C{callable}
  """
  from threading import Thread

  assert callable(main)

  Thread(target=main).start()
  exit_handler.run()
