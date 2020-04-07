import time
import queue
import os, signal
from web import app
from waitress import serve

from multiprocessing import Process, Queue, Event
from control.control import Control

PID_FILE = os.path.join(os.path.dirname(__file__), 'seedling.pid')


if __name__ == '__main__':

    pid = os.getpid()
    print('main pid %d' % pid)
    with open(PID_FILE, 'w') as f:
        f.write(str(pid))

    message_queue = Queue()
    response_queue = Queue()
    app.config['message_queue'] = message_queue
    app.config['response_queue'] = response_queue
    control = Control(message_queue, response_queue)

    control_proc = Process(target=control.main_loop, daemon=False)
    control_proc.start()
    print('control process started, daemon: %s' % control_proc.daemon)

    # serve(app, listen='0.0.0.0:8080')
    web_proc = Process(target=serve, args=(app,), kwargs={'listen': '0.0.0.0:8080'}, daemon=False)
    web_proc.start()
    print('web process started, daemon: %s' % web_proc.daemon)

    exit_event = Event()
    def term_handler(sig, context):
        exit_event.set()
        print('handler: %s' % sig)

    signal.signal(signal.SIGTERM, term_handler)

    while not exit_event.is_set():
        exit_event.wait(5)
        if control_proc.is_alive():
            print('control is alive')
        else:
            exit_event.set()
            print('control terminated')
        if web_proc.is_alive():
            print('web is alive')
        else:
            exit_event.set()
            print('web terminated')

    if web_proc.is_alive():
        print('terminate web')
        os.kill(web_proc.pid, signal.SIGTERM)

    if control_proc.is_alive():
        print('terminate control')
        message_queue.put('end')

    time.sleep(2)

    print('clear response queue')
    while True:
        try:
            response_queue.get_nowait()
        except queue.Empty:
            break

    print('clear message queue')
    while True:
        try:
            message_queue.get_nowait()
        except queue.Empty:
            break

    print('join web')
    web_proc.join()

    print('join control')
    control_proc.join()

    # try:
    #     os.remove(PID_FILE)
    # except FileNotFoundError:
    #     pass

    print('done')
    exit(0)
