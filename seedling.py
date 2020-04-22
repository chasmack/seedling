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
    print('seedling: pid %d' % pid)
    with open(PID_FILE, 'w') as f:
        f.write(str(pid))

    msg_queue = Queue()
    rsp_queue = Queue()
    app.config['msg_queue'] = msg_queue
    app.config['rsp_queue'] = rsp_queue
    control = Control(msg_queue, rsp_queue)

    control_proc = Process(target=control.main_loop, daemon=False)
    control_proc.start()
    # print('seedling: control process started, daemon: %s' % control_proc.daemon)

    # serve(app, listen='0.0.0.0:8080')
    web_proc = Process(target=serve, args=(app,), kwargs={'listen': '0.0.0.0:8080'}, daemon=False)
    web_proc.start()
    # print('seedling: web process started, daemon: %s' % web_proc.daemon)

    def signal_handler(sig, context):
        global exit_flag
        if sig == signal.SIGTERM:
            exit_flag = True

    signal.signal(signal.SIGTERM, signal_handler)

    exit_flag = False
    while not exit_flag:

        siginfo = signal.sigtimedwait([signal.SIGTERM], 5)
        if not control_proc.is_alive() or not web_proc.is_alive():
            exit_flag = True
        elif siginfo and siginfo.si_signo == signal.SIGTERM:
            exit_flag = True

    if web_proc.is_alive():
        print('seedling: terminate web')
        os.kill(web_proc.pid, signal.SIGTERM)

    if control_proc.is_alive():
        print('seedling: terminate control')
        clear_queue(msg_queue)
        msg_queue.put('end')

    # Give control loop time to update instrumentation
    time.sleep(2.5)

    print('seedling: clear queues')
    clear_queue(msg_queue)
    clear_queue(rsp_queue)

    print('seedling: join web')
    web_proc.join()

    print('seedling: join control')
    control_proc.join()

    print('seedling: shutdown input/output')
    shutdown()

    print('seedling: done')
    exit(0)
