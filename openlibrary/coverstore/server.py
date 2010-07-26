#! /usr/bin/env python
"""coverstore server.
"""

import sys
import yaml
import web

from openlibrary.coverstore import config, code, archive


def runfcgi(func, addr=('localhost', 8000)):
    """Runs a WSGI function as a FastCGI pre-fork server."""
    config = dict(web.config.get("fastcgi", {}))

    mode = config.pop("mode", None)
    if mode == "prefork":    
        import flup.server.fcgi_fork as flups
    else:
        import flup.server.fcgi as flups
        
    return flups.WSGIServer(func, multiplexed=True, bindAddress=addr, **config).run()

web.wsgi.runfcgi = runfcgi

def load_config(configfile):
    d = yaml.load(open(configfile))
    for k, v in d.items():
        setattr(config, k, v)

    if 'fastcgi' in d:
        web.config.fastcgi = d['fastcgi']

def main(configfile, *args):
    load_config(configfile)

    if '--archive' in args:
        archive.archive()
    else:
        sys.argv = [sys.argv[0]] + list(args)
        code.app.run()

if __name__ == "__main__":
    main(*sys.argv[1:])
