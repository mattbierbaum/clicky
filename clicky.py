#!/usr/bin/env python
import os
import simplejson
import time as timer
from operator import itemgetter
from itertools import tee, izip
import cPickle as pickle
from collections import defaultdict

import tornado.escape
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.websocket
from tornado.options import define, options

import zmq
from zmq.eventloop import ioloop, zmqstream

define("port", default=8000, help="run on the given port", type=int)
define("addr", default="127.0.0.1", help="listen address", type=str)

# out data structure (a LSH of positions and the times it was visited)
LOGFILE = "./clicky.log"
HH = 5+1
curr = (0,0)
time = 0
visits = defaultdict(list)
visits[curr].append(time)

# the valid moves that can be send to /in
mvs = {"u": [0,1], "d": [0,-1], "l": [-1,0], "r": [1,0]}

def toXY(visits):
    import numpy as np
    t, p = (list(t) for t in zip(*sorted(zip(visits.values(), visits.keys()))))
    timedict = {t:p for p,tt in visits.iteritems() for t in tt}
    ps = [timedict[i] for i in xrange(len(timedict.keys()))]
    ps = np.array(ps)
    return ps[:,0], ps[:,1]

def pairwise(iterable):
    a,b = tee(iterable)
    next(b,None)
    return izip(a,b)

def deduplicate(points):
    pairs = pairwise(points)
    seen = set()
    for (t1,x1,y1),(t2,x2,y2) in pairs:
        pair = ((x2,y2),(x1,y1)) if x1>x2 else ((x1,y1),(x2,y2))
        if pair not in seen:
            seen.add(pair)
            yield (t1,x1,y1)
            yield (t2,x2,y2)

def get_window():
    inside = []
    cx,cy = curr
    inside.extend( (t,x,y) for x,y in ( (cx+i,cy+j) for i in xrange(-HH,HH+1) for j in xrange(-HH,HH+1) ) for t in visits.get((x,y), [] ) )
    return list(deduplicate(sorted(inside, key=itemgetter(0))))

def loadlog():
    global visits, curr, time
    visits, curr, time = pickle.load(open(LOGFILE))
    
def logger():
    pickle.dump((visits,curr,time), open(LOGFILE, "w"), protocol=-1)

def blanklog():
    time, curr = 0, (0,0)
    visits = defaultdict(list)
    visits[curr].append(time)
    pickle.dump((visits,curr,time), open(LOGFILE, "w"), protocol=-1)

#====================================================
# all of the websocket handlers
#====================================================
class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/pts", SocketHandler),
        ]
        settings = dict(
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            gzip=True,
        )
        super(Application, self).__init__(handlers, **settings)

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("static/index.html")

class SocketHandler(tornado.websocket.WebSocketHandler):
    waiters = set()

    def initialize(self):
        pass

    def allow_draft76(self):
        return True

    def open(self):
        SocketHandler.waiters.add(self)
        self.write_message(simplejson.dumps(get_window()))
        self.write_message(simplejson.dumps((time, curr[0], curr[1])))

    def on_message(self, cmd):
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
           interesting_points.extend((t,x,y) for x,y in ((cx+tx,cy+HH) for tx in xrange(-HH,HH+1)) for t in visits.get((x,y),[]) )
           interesting_points.extend((t,x,y) for x,y in ((cx+tx,cy+HH+1) for tx in xrange(-HH,HH+1)) for t in visits.get((x,y),[]) )
        if cmd == 'd':
           interesting_points.extend((t,x,y) for x,y in ((cx+tx,cy-HH) for tx in xrange(-HH,HH+1)) for t in visits.get((x,y),[]) )
           interesting_points.extend((t,x,y) for x,y in ((cx+tx,cy-HH+1) for tx in xrange(-HH,HH+1)) for t in visits.get((x,y),[]) )
        if cmd == 'r':
           interesting_points.extend((t,x,y) for x,y in ((cx+HH,cy+ty) for ty in xrange(-HH,HH+1)) for t in visits.get((x,y),[]) )
           interesting_points.extend((t,x,y) for x,y in ((cx+HH+1,cy+ty) for ty in xrange(-HH,HH+1)) for t in visits.get((x,y),[]) )
        if cmd == 'l':
           interesting_points.extend((t,x,y) for x,y in ((cx-HH,cy+ty) for ty in xrange(-HH,HH+1)) for t in visits.get((x,y),[]) )
           interesting_points.extend((t,x,y) for x,y in ((cx-HH+1,cy+ty) for ty in xrange(-HH,HH+1)) for t in visits.get((x,y),[]) )
        interesting_points = sorted(interesting_points, key=itemgetter(0))

        # send the data back along the zmq sockets
        SocketHandler.send_updates(simplejson.dumps((time,cx,cy)))
        if len(interesting_points) > 0:
            interesting_points = list(deduplicate(interesting_points))
            SocketHandler.send_updates(simplejson.dumps(interesting_points))

        if False:
            time_end = timer.time()
            print "evaluation time: %e %i" % ((time_end - time_start), len(interesting_points))


    def on_close(self):
        SocketHandler.waiters.remove(self)

    @classmethod
    def send_updates(cls, msg):
        for waiter in cls.waiters:
            try:
                waiter.write_message(msg)
            except Exception as e:
                print e


# functions to add multiple clicky workers in the future
def pushpt(msg):
    SocketHandler.send_updates('pts', msg)

def install_zmq_hooks():
    ioloop.install()
    context = zmq.Context()
    ptsock = context.socket(zmq.SUB)
    ptsock.setsockopt(zmq.SUBSCRIBE, "")
    ptsock.connect ("tcp://localhost:%s" % 9000)
    ptstream = zmqstream.ZMQStream(ptsock)
    ptstream.on_recv(pushpt)


if __name__ == "__main__":
    loadlog()
    #tornado.web.ErrorHandler = webutil.ErrorHandler
    tornado.options.parse_command_line()
    app = Application()
    app.listen(options.port, options.addr)
    tornado.ioloop.PeriodicCallback(logger, 10000).start()
    tornado.ioloop.IOLoop.instance().start()

