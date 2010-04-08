"""
The Make module.  This module provides an interface to `make'.
"""
from __future__ import absolute_import

__all__ = ['clean_log', 'Make', 'env', 'make_target', 'mkdir', 'set_password',
           'SUCCESS']

def log_files(origin):
  """
     Creates the log file handler for the given port.  This is for both stdout
     and stderr.

     @param origin: The ports origin
     @type origin: C{str}
     @return: The stdout and stderr file handlers
     @rtype: C{(file, file)}
  """
  from os.path import join

  from .env import dirs

  log = open(join(dirs['log_port'], origin.replace('/', '_')), 'a')
  return log, log

def cmdtostr(args):
  """
     Convert a list of arguments to a single string.

     @param args: The list of arguments
     @type args: C{[str]}
     @return: The arguments as a string
     @rtype: C{str}
  """
  argstr = []
  for i in args:
    argstr.append(i.replace("\\", "\\\\").replace('"', '\\"').\
                    replace("'", "\\'").replace('\n', '\\\n'))
    if ' ' in i or '\t' in i or '\n' in i:
      argstr[-1] = '"%s"' & argstr[-1]
  return ' '.join(argstr)

def get_pipe(pipe, origin):
  """
     Returns the appropriate pipes.  None is the default (pipe to logfile),
     False is not piping, True is pipe stdout and stderr and file object is
     pipe to the file (both stdout and stderr)

     @param pipe: The type of pipe requested
     @type pipe: C{bool|None|file}
     @param origin: The for for which to run create logfiles for
     @type origin: C{str}
     @return: Tuple of pipes (stdin, stdout, stderr)
     @rtype: C{(None|PIPE|file}
  """
  from subprocess import PIPE, STDOUT

  if pipe is True:
    # Pipe is required
    return PIPE, PIPE, STDOUT
  elif pipe:
    # Pipe to the requested stream
    return PIPE, pipe, STDOUT
  elif pipe is False:
    # No piping allowed (requires user input/output)
    return None, None, None
  else:
    # Default: Log the output of the process
    stdout, stderr = log_files(origin)
    return PIPE, stdout, stderr


class Make(object):
  """
     The make class.  This class handles executing make targets.
  """

  SUCCESS = 0     #: Return code apon success
  no_opt = False  #: Indicate if we should not issue a command

  def __init__(self):
    """
       Initialise the Make class.
    """
    from logging import getLogger
    from os import getenv, getuid

    self.env = {}  #: The environment flags to pass to make, aka -D...
    self.pre_cmd = []  #: Prepend to command

    self._log = getLogger('pypkg.make')  #: Logger for this class

    self.__am_root = getuid()  #: Indicate if we are root
    self.__password = None  #: Password to access root status (via su or sudo)

    self.env["PORTSDIR"] = getenv("PORTSDIR", "/usr/ports") #: Location of port
    self.env["BATCH"] = None  #: Default to use batch mode
    self.env["NOCLEANDEPENDS"] = None  #: Default to only clean ports
    self.env["NO_DEPENDS"] = None  #: Do not try and resolve dependencies

  def mkdir(self, path):
    """
       Create a directory writable by this process.

       @param path: The directory to create
       @type path: C{str}
       @return: If the creation was successful
       @rtype: C{bool}
    """
    from os.path import exists, isdir
    from os import getuid, getgid
    from subprocess import Popen, PIPE, STDOUT

    from .env import iswritable

    if isdir(path) and iswritable(path):
      return True
    elif isinstance(self.__am_root, int) or exists(path):
      return False

    self._log.debug("Creating directory (uid=%i:gid=%i): %s" %
                                                    (getuid(), getgid(), path))
    cmd = Popen(self.__am_root + ['install', '-d', '-g%i' % getgid(),
                                  '-o%i' % getuid(), path], close_fds=True,
                                  stdin=PIPE, stdout=PIPE, stderr=STDOUT)
    # Send the password to sudo and close the pipe
    cmd.stdin.write(self.__password)
    cmd.stdin.close()

    return cmd.wait() is Make.SUCCESS

  def set_password(self, passwd):
    """
      Check the password to gain root status.  If the password is correct then
      it is stored locally.

      @param passwd: The password to use.
      @type passwd: C{str}
      @return: If the password gets us user privilege
      @rtype: C{bool}
    """
    from subprocess import Popen, PIPE, STDOUT

    # If we are the superuser or already have the password return
    if self.__am_root == 0 or self.__password is not None:
      return True

    try:
      # Try running sudo with a simple command (cat)
      sudo = ['sudo', '-S', '--']
      cmd = Popen(sudo + ['cat'], stdin=PIPE, stdout=PIPE, stderr=STDOUT,
                                          close_fds=True)
      # Send the password to sudo and close the pipe
      cmd.stdin.write(passwd)
      cmd.stdin.close()

      # Check if sudo succeeded
      if cmd.wait() is Make.SUCCESS:
        self.__am_root = sudo
        self.__password = passwd
        self._log.info("Sudo password approved: ``***''")
        return True
      else:
        self._log.warn("Incorrect sudo password: ``%s''" % passwd)
        return False
    except OSError:
      # SUDO does not exist, try su?
      self._log.error("Unable to execute sudo (not installed?)")
      return None

  def target(self, origin, args, pipe=None, priv=False, block=True):
    """
      Run make to build a target with the given arguments and the appropriate
      addition settings.

      @param origin: The port for which to run make
      @type origin: C{str}
      @param args: Targets and arguments for make
      @type args: C{(str)}
      @param pipe: Indicate if the make argument output must be piped
      @type pipe: C{bool|file}
      @param priv: Indicate if the make command needs to be privileged
      @type priv: C{bool}
      @param block: If must wait for pipe lock
      @type block: C{bool}
      @return: The make process interface
      @rtype: C{Popen}
    """
    from os.path import join
    from subprocess import Popen

    if isinstance(args, str):
      args = [args]
    # Add all the environment variables to the argument
    # Include PORTSDIR if it is not the default
    # Include BATCH if the target is not 'config'
    # Include NOCLEANDEPENDS if the target includes 'clean'
    args = args + [v and '%s=%s' % (k, v) or "-D%s" % k for k, v in
                  self.env.items() if (k, v) != ("PORTSDIR", "/usr/ports") and
                      (args[0], k) != ('config', "BATCH") and
                      (k != "NOCLEANDEPENDS" or 'clean' in args)]

    # Get the appropriate pipes
    stdin, stdout, stderr = get_pipe(pipe, origin)

    # Pause the monitor if piping is prohibited and targets are operational
    # This allows unrestricted access to the console (and acts as a lock)
    if pipe is False and not Make.no_opt:
      from .monitor import monitor
      if not monitor.pause(block):
        return None

    try:
      args = self.pre_cmd + ['make', '-C',
                                     join(self.env["PORTSDIR"], origin)] + args
      if pipe or not Make.no_opt:
        # If privilage is required and we have a pre_cmd to gain privilage
        if priv and isinstance(self.__am_root, (list, tuple)):
          args = self.__am_root + args
        self._log.debug("Executing: ``%s''" % cmdtostr(args))
        pmake = Popen(args, stdin=stdin, stdout=stdout, stderr=stderr,
                    close_fds=True)
        if stdin:
          # Send the password to sudo (if appropriate)
          if priv and isinstance(self.__am_root, (list, tuple)):
            pmake.stdin.write(self.__password)
          # Close the input stream (not used)
          pmake.stdin.close()
        elif pipe is False:
          # Wait for the process to finish, otherwise we get overlaps...
          pmake.wait()
      else:
        # If we are not operating print the command and return the dummy process
        print cmdtostr(args)
        pmake = PopenNone()
    finally:
      if pipe is False and not Make.no_opt:
        monitor.resume()

    return pmake

make = Make()

env = make.env                   #: Environment variables for make
make_target = make.target        #: Execute the given target
mkdir = make.mkdir               #: Create a directory writable by this process
set_password = make.set_password #: Set the password to execute privileged cmds
SUCCESS = Make.SUCCESS           #: Returns by a process upon success.

class PopenNone(object):
  """
     An empty replacement for Popen.
  """

  returncode = SUCCESS  #: Return code for the dummy processes
  pid = -1              #: PID of the dummy processes

  stdin  = None  #: Stdin stream
  stdout = None  #: Stdout stream
  stderr = None  #: Stderr stream

  @staticmethod
  def wait():
    """
       Return SUCCESS.

       @return: Success
       @rtype: C{int}
    """
    return PopenNone.returncode

  @staticmethod
  def poll():
    """
       Return SUCCESS.

       @return: Success
       @rtype: C{int}
    """
    return PopenNone.returncode

  @staticmethod
  def communicate(input=None):
    """
       Communicate with the process.

       @param input: Input to the port
       @type input: C{str}
       @return: The processes output
       @rtype: C{(None, None)}
    """
    return (PopenNone.stdout, PopenNone.stderr)
