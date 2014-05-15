Clicky
=======

[Clicky online](http://mattbierbaum.com)

The collective motion control experiment, now in Python, tornado, flot, and
zmq.  The newest version allows for a clicky cluster where workers handle
different user connections and communicate through zmq.  To easily set up
a clicky cluster on nginx, simply spin up several clicky daemons:

    python clicky.py --port=8000
    python clicky.py --port=8001

after configuring the correct addresses in clicky.py itself.  Then, in
the nginx configurations, add a load balancing upstream, and proxypass
all connections to clicky:

    upstream cluster {
        server 127.0.0.1:8000;
        server 127.0.0.1:8001;
    }

    location / { 
        proxy_http_version 1.1;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $http_host;
        proxy_set_header X-NginX-Proxy true;

        proxy_pass http://cluster;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
    }

Enjoy, you now have a clicky server.
