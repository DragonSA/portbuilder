"""
The Tools module.  This module contains various utilities (that should be in
the standard libraries) for ease of programming...
"""

# TODO: Move into main module (__init__)
def run_main(main):
  """
     Run the main function in its own thread and then runs the exit handler
     function.  This function does not return.

     @param main: The main function to execute
     @type main: C{callable}
  """
  from exit import exit_handler, terminate
  from threading import Thread

  assert callable(main)

  def call():
    """
       Call the main function and then start the idle checker.
    """
    try:
      main()
    except SystemExit:
      terminate()
    except BaseException:
      from logging import getLogger
      getLogger("pypkg").exception("Main function failed")
      terminate()
    finally:
      exit_handler.start()

  Thread(target=call).start()
  exit_handler.run()
