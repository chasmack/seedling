import time
import posix_ipc
import sqlite3

from flask import request
from flask import render_template, flash

from seedling import app

@app.route('/test', methods=['GET'])
def test():
    return 'test'

@app.route('/', methods=['GET'])
def seedling():

    msg = request.args.get('msg', '').upper()
    if msg != '':

        mq = posix_ipc.MessageQueue(app.config['MQUEUE_CMD'])
        success = False
        try:
            # this fails after timeout if the queue is full
            mq.send(msg, timeout=5)

            # wait for the controller to pick up the message
            for i in range(10):
                if mq.current_messages == 0:
                    success = True
                    break
                time.sleep(0.500)

        except posix_ipc.BusyError:
            pass

        mq.close()

        if success:
            flash(msg, 'success')
        else:
            flash('NO CONTROLLER', 'error')

    con = sqlite3.connect(app.config['DATABASE'])
    cur = con.cursor()
    cur.execute("""
    WITH
    t1 AS (SELECT dt, temp FROM temperature WHERE id = 'C1' ORDER BY dt DESC LIMIT 60),
    t2 AS (SELECT dt, temp FROM temperature WHERE id = 'C2' ORDER BY dt DESC LIMIT 60),
    t3 AS (SELECT dt, temp FROM temperature WHERE id = 'C3' ORDER BY dt DESC LIMIT 60),
    t4 AS (SELECT dt, temp FROM temperature WHERE id = 'C4' ORDER BY dt DESC LIMIT 60),
    t5 AS (SELECT dt, temp FROM temperature WHERE id = 'C5' ORDER BY dt DESC LIMIT 60)
    SELECT strftime('%H:%M:%S', t1.dt) "time",
      printf('%0.1f', t1.temp) "t1",
      printf('%0.1f', t2.temp) "t2",
      printf('%0.1f', t3.temp) "t3",
      printf('%0.1f', t4.temp) "t4",
      printf('%0.1f', t5.temp) "t5"
    FROM t1
    LEFT JOIN t2 USING (dt)
    LEFT JOIN t3 USING (dt)
    LEFT JOIN t4 USING (dt)
    LEFT JOIN t5 USING (dt)
    ORDER BY dt DESC;
    """)

    temps = cur.fetchall()

    cur.execute("""
    WITH
    A AS (SELECT dt, state, duty FROM relay WHERE id = 'A' ORDER BY dt DESC LIMIT 1),
    B AS (SELECT dt, state, duty FROM relay WHERE id = 'B' ORDER BY dt DESC LIMIT 1),
    C AS (SELECT dt, state, duty FROM relay WHERE id = 'C' ORDER BY dt DESC LIMIT 1),
    D AS (SELECT dt, state, duty FROM relay WHERE id = 'D' ORDER BY dt DESC LIMIT 1)
    SELECT
      printf('%.2f', A.duty) "duty_A",
      printf('%.2f', B.duty) "duty_B",
      printf('%.2f', C.duty) "duty_C",
      printf('%.2f', D.duty) "duty_D"
    FROM A
    LEFT JOIN B USING (dt)
    LEFT JOIN C USING (dt)
    LEFT JOIN D USING (dt)
    """)

    relays = cur.fetchone()

    con.close()

    return render_template('seedling.html', relays=relays, temps=temps)


#
# HTTP error handlers
#

@app.errorhandler(400)
def bad_request(e):
    return render_template('400.html'), 400

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500
