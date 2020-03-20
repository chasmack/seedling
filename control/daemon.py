"""Generic linux daemon base class for python 3.x."""

import sys, os, time, atexit, signal
import logging


class daemon:
    """A generic daemon class.

    Usage: subclass the daemon class and override the run() method."""

    def __init__(self, pidfile):
        self.pidfile = pidfile

    def daemonize(self):
        """Deamonize class. UNIX double fork mechanism."""

        logging.debug('Daemonize process.')

        try:
            pid = os.fork()
            if pid > 0:
                # exit first parent
                sys.exit(0)

        except OSError as err:
            logging.error('fork #1 failed: %s', err)
            sys.exit(1)

        logging.debug('First child running: pid=%d', os.getpid())

        # decouple from parent environment
        os.chdir('/')
        os.setsid()
        os.umask(0)

        # do second fork
        try:
            pid = os.fork()
            if pid > 0:
                # exit from second parent
                sys.exit(0)

        except OSError as err:
            logging.error('fork #2 failed: %s', err)
            sys.exit(1)

        logging.debug('Second child running: pid=%d', os.getpid())

        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = open(os.devnull, 'r')
        so = open(os.devnull, 'a+')
        se = open(os.devnull, 'a+')

        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        # write pidfile
        atexit.register(self.delpid)

        pid = str(os.getpid())
        logging.debug('Write pid file: %s', self.pidfile)
        with open(self.pidfile, 'w+') as f:
            f.write(pid + '\n')

        logging.debug('Daemonize complete.')

    def delpid(self):
        logging.debug('Deleting pidfile: %s', self.pidfile)
        os.remove(self.pidfile)

    def start(self):
        """Start the daemon."""

        # Check for a pidfile to see if the daemon already runs
        try:
            with open(self.pidfile, 'r') as pf:
                pid = int(pf.read().strip())

        except IOError:
            pid = None

        if pid:
            logging.error('pidfile %s exists. Daemon already running?', self.pidfile)
            sys.exit(1)

        # Start the daemon
        if self.daemon_process:
            self.daemonize()
        self.run()

    def kill(self):
        """Kill the daemon. Stop is implemented with the message queue."""

        # Get the pid from the pidfile
        try:
            with open(self.pidfile, 'r') as pf:
                pid = int(pf.read().strip())
        except IOError:
            pid = None

        if not pid:
            logging.warning('pidfile %s does not exist. Daemon not running?', self.pidfile)
            return  # not an error in a restart

        # Try killing the daemon process
        try:
            while 1:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.1)
        except OSError as err:
            e = str(err.args)
            if e.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                logging.error('Error killing daemon: %s', str(err.args))
                sys.exit(1)

    def run(self):
        """You should override this method when you subclass Daemon.

        It will be called after the process has been daemonized by
        start() or restart()."""
