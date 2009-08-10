"""
The pypkg module.
"""

from __future__ import absolute_import

def run_main(main):
  """
     Run the main function in its own thread and then runs the exit handler
     function.  This function does not return.

     @param main: The main function to execute
     @type main: C{callable}
  """
  from .threads import Thread

  from .exit import exit_handler, start, terminate

  assert callable(main)

  def call():
    """
       Call the main function and then start the idle checker.
    """
    try:
      main()
      start()
    except SystemExit:
      terminate()
    except BaseException:
      from logging import getLogger
      getLogger("pypkg").exception("Main function failed")
      terminate()

  Thread(target=call, name="Main").start()
  exit_handler.run()
