#! /usr/bin/env python
"""Fastcgi multiplexer.

Request to /host1:port1/path is redirected to fastcgi://host1:port1/path.
"""
from flup.client.fcgi_app import FCGIApp
from flup.server.fcgi import WSGIServer
import socket
import sys, re

stderr = sys.stderr

re_host = re.compile("^/([a-zA-Z0-9\.]*):(\d+)(/.*)$")

def proxy(env, start_response):
    env = dict(env)
    m = re_host.match(env['PATH_INFO'])
    if not m:
        start_response("404 Not Found", [])
        return "not found"

    host, port, env['PATH_INFO'] = m.groups()
    env['REQUEST_URI'] = env['REQUEST_URI'][len('/%s:%s' % (host, port)):]
    
    try:
        app = FCGIApp(connect=(host, int(port)))
        return app(env, start_response)
    except socket.error:
        start_response("503 Service not available", [])
        return "Service not available"

def main():
    import sys
    args = sys.argv[1:] or ["8080"]
    port = int(args[0])
    print "fcgi multiplexer is running at http://localhost:%d" % port
    return WSGIServer(proxy, bindAddress=("localhost", port)).run()

if __name__ == "__main__":
    main()
