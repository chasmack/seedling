import time
import queue
import os, signal
from web import app
from waitress import serve

from multiprocessing import Process, Queue
from control.control import Control, shutdown

PID_FILE = os.path.join(os.path.dirname(__file__), 'seedling.pid')

def clear_queue(q):
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            break

if __name__ == '__main__':

    pid = os.getpid()
    print('main pid %d' % pid)
    with open(PID_FILE, 'w') as f:
        f.write(str(pid))

    mqueue = Queue()
    rqueue = Queue()
    app.config['mqueue'] = mqueue
    app.config['rqueue'] = rqueue
    control = Control(mqueue, rqueue)

    control_proc = Process(target=control.main_loop, daemon=False)
    control_proc.start()
    print('main control process started, daemon: %s' % control_proc.daemon)

    # serve(app, listen='0.0.0.0:8080')
    web_proc = Process(target=serve, args=(app,), kwargs={'listen': '0.0.0.0:8080'}, daemon=False)
    web_proc.start()
    print('main web process started, daemon: %s' % web_proc.daemon)

    def term_handler(sig, context):
        global exit_flag
        exit_flag = True
        print('main handler for %s' % sig)
    signal.signal(signal.SIGTERM, term_handler)

    exit_flag = False
    while not exit_flag:

        siginfo = signal.sigtimedwait([signal.SIGTERM], 5)
        if siginfo is None and control_proc.is_alive() and web_proc.is_alive():
            pass
        else:
            exit_flag = True

    if web_proc.is_alive():
        print('main terminate web')
        os.kill(web_proc.pid, signal.SIGTERM)

    if control_proc.is_alive():
        print('main terminate control')
        clear_queue(mqueue)
        mqueue.put('end')

    # Give control loop time to update instrumentation
    time.sleep(2.5)

    print('main clear message queue')
    clear_queue(mqueue)

    print('main clear response queue')
    clear_queue(rqueue)

    print('main join web')
    web_proc.join()

    print('main join control')
    control_proc.join()

    print('main shutdown input/output')
    shutdown()

    print('main done')
    exit(0)
