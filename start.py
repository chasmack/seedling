from seedling import app
from waitress import serve

if __name__ == '__main__':

    # app.run(host='0.0.0.0', port=8080, debug=True)
    # serve(app, listen='0.0.0.0:80', url_prefix='/tools')
    serve(app, listen='0.0.0.0:8080')
