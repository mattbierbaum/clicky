import gevent
import time as timer
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

def deduplicate(points):
    tseg, tpts = {}, []
    for i in xrange(len(points)-1):
        currpoint = points[i]
        nextpoint = points[i+1]
        tup = (currpoint[-2:], nextpoint[-2:])
        if not tseg.get(tup, None):
            tseg[tup] = 1
            tpts.append(currpoint)
            tpts.append(nextpoint)
    return tpts

def get_window():
    inside = []
    cx,cy = curr
    inside.extend( (t,x,y) for x,y in ( (cx+i,cy+j) for i in xrange(-6,7) for j in xrange(-6,7) ) for t in visits.get((x,y), [] ) )
    return deduplicate(inside)

@app.route("/window")
def handle_window():
    if request.environ.get("wsgi.websocket"):
        ws = request.environ['wsgi.websocket']

        rx_wsock = context.socket(zmq.SUB)
        rx_wsock.setsockopt(zmq.SUBSCRIBE, "")
        rx_wsock.connect('inproc://window')

        # send the initial window
        ws.send(simplejson.dumps(get_window()))
        while True:
            msg = rx_wsock.recv()
            if msg is None:
                break
            ws.send(msg)
    return ""

@app.route("/out")
def handle_out():
    if request.environ.get("wsgi.websocket"):
        ws = request.environ['wsgi.websocket']

        rx_dsock = context.socket(zmq.SUB)
        rx_dsock.setsockopt(zmq.SUBSCRIBE, "")
        rx_dsock.connect('inproc://data')
       
        # send the initial update point
        ws.send(simplejson.dumps((time,curr[0],curr[1])))
        while True:
            msg = rx_dsock.recv()
            if msg is None:
                break
            ws.send(msg)
    return ""

@app.route("/in")
def handle_in():
    if request.environ.get("wsgi.websocket"):
        ws = request.environ['wsgi.websocket']
        while True:
            msg = ws.receive()
            if msg is None:
                break
            handle_newpt(msg)
    return ""

def handle_newpt(cmd=None):
    time_start = timer.time()

    global time, visits, curr
    try:
        dx,dy = mvs[cmd]
    except KeyError as e:
        return 

    # find out next point
    ox,oy = curr
    curr  = (ox+dx, oy+dy)
    cx,cy = curr

    # these two statements belong together
    time = time + 1
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
    interesting_points = sorted(interesting_points, key=itemgetter(0))

    # send the data back along the zmq sockets
    tx_dsock.send(simplejson.dumps((time,cx,cy)))
    if len(interesting_points) > 0:
        tx_wsock.send(simplejson.dumps(deduplicate(interesting_points)))

    if app.debug == True:
        time_end = timer.time()
        print "evaluation time: %e" % (time_end - time_start)

@app.route("/<path:path>")
def handle_file(path=None):
    return send_from_directory("./static", path)

@app.route("/")
def handle_index():
    return send_from_directory("./static", "index.html")

if __name__ == "__main__":
    http_server = WSGIServer(('',8000), app, handler_class=WebSocketHandler)
    http_server.serve_forever()
