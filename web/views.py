import queue

from flask import request
from flask import render_template, flash

from web import app

@app.route('/test', methods=['GET'])
def test():
    return 'test'

@app.route('/', methods=['GET'])
def seedling():

    msg = request.args.get('msg', '')
    mqueue = app.config['mqueue']
    if msg != '':
        mqueue.put(msg)
    else:
        mqueue.put('stat')

    rqueue = app.config['rqueue']
    try:
        status = rqueue.get(timeout=5.0)
    except queue.Empty:
        flash('ERROR: No response from controller.', 'error')
        status = ()

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
