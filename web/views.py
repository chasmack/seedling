import queue

from flask import request
from flask import render_template, flash
from flask.json import jsonify, dumps

from web import app

@app.route('/stat', methods=['GET'])
def stat():

    app.config['msg_queue'].put('stat')
    try:
        rsp = app.config['rsp_queue'].get(timeout=5.0)
    except queue.Empty:
        rsp = {'error': 'No response from controller.'}

    return jsonify(rsp)

@app.route('/', methods=['GET'])
def seedling():

    msg = request.args.get('msg')
    if msg:
        app.config['msg_queue'].put(msg)
        try:
            rsp = app.config['rsp_queue'].get(timeout=5.0)
        except queue.Empty:
            rsp = {'error': 'No response from controller.'}

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(rsp)

        elif rsp['error']:
            flash(rsp['error'], 'error')

    return render_template('seedling.html')

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
