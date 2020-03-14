from flask import Flask

app = Flask(__name__)

# configuration
DEBUG = False
DATABASE = '/home/pi/projects/seedling/data/status.sqlite'
MQUEUE_CMD = '/grow_command'
MQUEUE_RESP = '/grow_response'

# import os
# os.urandom(24)
SECRET_KEY = b'A&\x04\x935\\I`\x17\x94\xb8CO\x86\xc1\x0c0L\x86\x1d\x96\x97\xa7\xd1'

# app.config.from_envvar('FLASKAPP_CONFIG', silent=False)
app.config.from_object(__name__)

import seedling.views

@app.before_request
def before_request():
    pass

@app.after_request
def after_request(response):
    return response

@app.teardown_request
def teardown_request(exception):
    pass

@app.teardown_appcontext
def teardown_appcontext(exception):
    pass
