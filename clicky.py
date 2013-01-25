import gevent
import simplejson
from collections import defaultdict
from operator import itemgetter
from gevent.pywsgi import WSGIServer
from gevent_zeromq import zmq
from geventwebsocket import WebSocketHandler, WebSocketError
from flask import make_response, Flask, request, render_template, send_from_directory

# FIXME - include a pool so there is a max number of gets
context = zmq.Context()
app = Flask(__name__)
app.debug = True

# out data structure (a LSH of positions and the times it was visited)
curr = (0,0)
time = 0
visits = defaultdict(list)
visits[curr].append(time)

# the valid moves that can be send to /in
mvs = {"u": [0,1], "d": [0,-1], "l": [-1,0], "r": [1,0]}

tx_dsock = context.socket(zmq.PUB)
tx_dsock.bind("inproc://data")
tx_wsock = context.socket(zmq.PUB)
tx_wsock.bind("inproc://window")

rx_dsock = context.socket(zmq.SUB)
rx_dsock.setsockopt(zmq.SUBSCRIBE, "")
rx_dsock.connect('inproc://data')
rx_wsock = context.socket(zmq.SUB)
rx_wsock.setsockopt(zmq.SUBSCRIBE, "")
rx_wsock.connect('inproc://window')

def get_window():
    inside = []
    cx,cy = curr
    inside.extend( (t,x,y) for x,y in ( (cx+i,cy+j) for i in xrange(-6,7) for j in xrange(-6,7) ) for t in visits.get((x,y), [] ) )
    return inside

@app.route("/window")
def handle_window():
    if request.environ.get("wsgi.websocket"):
        ws = request.environ['wsgi.websocket']

        # send the initial window
        ws.send(simplejson.dumps(get_window()))
        while True:
            msg = rx_wsock.recv()
            ws.send(msg)

@app.route("/out")
def handle_out():
    if request.environ.get("wsgi.websocket"):
        ws = request.environ['wsgi.websocket']
       
        # send the initial update point
        ws.send(simplejson.dumps((time,curr[0],curr[1])))
        while True:
            msg = rx_dsock.recv()
            ws.send(msg)

@app.route("/in")
def handle_in():
    if request.environ.get("wsgi.websocket"):
        ws = request.environ['wsgi.websocket']
        while True:
            msg = ws.receive()
            handle_newpt(msg)
    
def handle_newpt(cmd=None):
    global time, visits, curr
    try:
        dx,dy = mvs[cmd]
    except KeyError as e:
        return 

    time = time + 1
    curr = (curr[0]+dx, curr[1]+dy)
    cx,cy = curr

    visits[curr].append(time)

    # we need a set of tuples (time, x,y) 
    interesting_points = []
    if cmd == 'u':
       interesting_points.extend( (t,x,y) for x,y in ( (cx+tx,cy+6) for tx in xrange(-6,7) ) for t in visits.get((x,y),[]) )
    if cmd == 'd':
       interesting_points.extend( (t,x,y) for x,y in ( (cx+tx,cy-6) for tx in xrange(-6,7) ) for t in visits.get((x,y),[]) )
    if cmd == 'r':
       interesting_points.extend( (t,x,y) for x,y in ( (cx+6,cy+ty) for ty in xrange(-6,7) ) for t in visits.get((x,y),[]) )
    if cmd == 'l':
       interesting_points.extend( (t,x,y) for x,y in ( (cx-6,cy+ty) for ty in xrange(-6,7) ) for t in visits.get((x,y),[]) )

    #interesting_points = sorted(interesting_points, key=itemgetter(0) )
    tx_dsock.send(simplejson.dumps((time,cx,cy)))
    if len(interesting_points) > 0:
        tx_wsock.send(simplejson.dumps(interesting_points))

@app.route("/<path:path>")
def handle_file(path=None):
    return send_from_directory("./static", path)

@app.route("/")
def handle_index():
    return send_from_directory("./static", "index.html")

if __name__ == "__main__":
    http_server = WSGIServer(('',8000), app, handler_class=WebSocketHandler)
    http_server.serve_forever()
