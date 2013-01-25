import gevent
import simplejson
from gevent.pywsgi import WSGIServer
from gevent_zeromq import zmq
from geventwebsocket.handler import WebSocketHandler
from flask import make_response, Flask, request, render_template, send_from_directory

# FIXME - include a pool so there is a max number of gets
# FIXME - spatial data structure for quick loading

context = zmq.Context()
app = Flask(__name__)
points = [[0,0]]

qsock = context.socket(zmq.PUB)
qsock.bind("inproc://data")

@app.route("/out")
def handle_out():
    if request.environ.get("wsgi.websocket"):
        ws = request.environ['wsgi.websocket']
        ssock = context.socket(zmq.SUB)
        ssock.setsockopt(zmq.SUBSCRIBE, "")
        ssock.connect('inproc://data')
        for p in points[-100:]:
            ws.send(simplejson.dumps(p))
        while True:
            msg = ssock.recv()
            ws.send(msg)
    return 

@app.route("/in")
def handle_in():
    if request.environ.get("wsgi.websocket"):
        ws = request.environ['wsgi.websocket']
        while True:
            msg = ws.receive()
            handle_newpt(msg)
    return 
    
def handle_newpt(cmd=None):
    mvs = {"u": [0,1], "d": [0,-1], "l": [-1,0], "r": [1,0]}
    x,y = mvs[cmd]
    cx,cy = points[-1]

    points.append([cx+x,cy+y])
    qsock.send(simplejson.dumps(points[-1]))
    return "."

@app.route("/<path:path>")
def handle_file(path=None):
    return send_from_directory("./static", path)

@app.route("/")
def handle_index():
    return send_from_directory("./static", "index.html")

if __name__ == "__main__":
    http_server = WSGIServer(('',8000), app, handler_class=WebSocketHandler)
    http_server.serve_forever()
