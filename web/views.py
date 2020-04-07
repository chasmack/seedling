import time
import queue
import sqlite3

from flask import request
from flask import render_template, flash

from web import app

@app.route('/test', methods=['GET'])
def test():
    return 'test'

@app.route('/', methods=['GET'])
def seedling():

    msg = request.args.get('msg', '')
    message_queue = app.config['message_queue']
    if msg != '':
        message_queue.put(msg)
    else:
        message_queue.put('stat')

    response_queue = app.config['response_queue']
    try:
        status = response_queue.get(timeout=5.0)
    except queue.Empty:
        status = ()
        flash('ERROR: No response from controller.', 'error')

    return render_template('seedling.html', status=status)

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
