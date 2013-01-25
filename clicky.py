import gevent
import simplejson
from collections import defaultdict
from operator import itemgetter
from gevent.pywsgi import WSGIServer
from gevent_zeromq import zmq
from geventwebsocket.handler import WebSocketHandler
from flask import make_response, Flask, request, render_template, send_from_directory

# FIXME - include a pool so there is a max number of gets
# FIXME - spatial data structure for quick loading

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

dsock = context.socket(zmq.PUB)
dsock.bind("inproc://data")

wsock = context.socket(zmq.PUB)
wsock.bind("inproc://window")

@app.route("/window")
def handle_window():
    if request.environ.get("wsgi.websocket"):
        ws = request.environ['wsgi.websocket']
        ssock = context.socket(zmq.SUB)
        ssock.setsockopt(zmq.SUBSCRIBE, "")
        ssock.connect('inproc://window')
        for p,ts in visits.iteritems():
            for t in ts:
                ws.send(simplejson.dumps((t,p[0],p[1])))
        while True:
            msg = ssock.recv()
            ws.send(msg)
    return 


@app.route("/out")
def handle_out():
    if request.environ.get("wsgi.websocket"):
        ws = request.environ['wsgi.websocket']
        ssock = context.socket(zmq.SUB)
        ssock.setsockopt(zmq.SUBSCRIBE, "")
        ssock.connect('inproc://data')
        for p,ts in visits.iteritems():
            for t in ts:
                ws.send(simplejson.dumps((t,p[0],p[1])))
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
    global time, visits, curr
    dx,dy = mvs[cmd]
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
    dsock.send(simplejson.dumps((time,cx,cy)))
    for pt in interesting_points:
        print "window:", pt
        wsock.send(simplejson.dumps(pt))

def handle_newwindow(websocket):
    pass

@app.route("/<path:path>")
def handle_file(path=None):
    return send_from_directory("./static", path)

@app.route("/")
def handle_index():
    return send_from_directory("./static", "index.html")

if __name__ == "__main__":
    http_server = WSGIServer(('',8000), app, handler_class=WebSocketHandler)
    http_server.serve_forever()
