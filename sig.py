import time
import queue
import os, signal
from web import app
from waitress import serve

from multiprocessing import Process, Queue, Event

class Control:
    def __init__(self, mqueue):
        self.mqueue = mqueue

    def main_loop(self):

        self.run = True
        while self.run:
            print('sleep')
            try:
                msg = self.mqueue.get(timeout=5)
                print('msg: %s' % msg)
                if msg == 'end':
                    self.run = False
            except queue.Empty:
                print('no msg')

            print('loop')
        print('exiting')

if __name__ == '__main__':

    pid = os.getpid()
    print('main pid %d' % pid)

    mqueue = Queue()
    control = Control(mqueue)

    control_proc = Process(target=control.main_loop, daemon=False)
    control_proc.start()
    print('control process started, daemon: %s' % control_proc.daemon)


    exit_flag = False
    while not exit_flag:
        if signal.sigtimedwait([signal.SIGTERM], 10) is None:
            # No SIGTERM, check children are still running
            if control_proc.is_alive():
                print('control is alive')
            else:
                print('control terminated')
                exit_flag = True
        else:
            print('SIGTERM')
            exit_flag = True

    if control_proc.is_alive():
        print('sending end')
        mqueue.put('end')

    print('join control')
    control_proc.join()

    print('done')
    exit(0)
