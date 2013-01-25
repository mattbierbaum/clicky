import gevent
import simplejson
from gevent.pywsgi import WSGIServer
from gevent_zeromq import zmq
from geventwebsocket.handler import WebSocketHandler
from flask import make_response, Flask, request, render_template

context = zmq.Context()
app = Flask(__name__)
points = [[0,0],[1,0],[1,1],[0,1],[0,0]]

sock = context.socket(zmq.PUB)
sock.bind("inproc://data")

@app.route("/datastream")
def handle_datastream():
    if request.environ.get("wsgi.websocket"):
        ws = request.environ['wsgi.websocket']
        sock = context.socket(zmq.SUB)
        sock.setsockopt(zmq.SUBSCRIBE, "")
        sock.connect('inproc://data')
        for p in points:
            ws.send(simplejson.dumps(p))
        while True:
            msg = sock.recv()
            ws.send(msg)
    return 

@app.route("/pt/<x>/<y>")
def handle_newpt(x=0, y=0):
    c = points[-1]
    points.append([c[0]+int(x),c[1]+int(y)])
    sock.send(simplejson.dumps(points[-1]))
    return "ok"

@app.route("/<path:path>")
def handle_file(path=None):
    return render_template(path)

@app.route("/")
def handle_index():
    return render_template("index.html")

if __name__ == "__main__":
    http_server = WSGIServer(('',8000), app, handler_class=WebSocketHandler)
    http_server.serve_forever()
