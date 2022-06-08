#!/usr/bin/env python
"""coverstore server.
"""

import sys
import yaml
import web

from openlibrary.coverstore import config, code, archive
from openlibrary.utils.sentry import Sentry


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
    with open(configfile) as in_file:
        d = yaml.safe_load(in_file)
    for k, v in d.items():
        setattr(config, k, v)

    if 'fastcgi' in d:
        web.config.fastcgi = d['fastcgi']


def setup(configfile: str) -> None:
    load_config(configfile)

    sentry = Sentry(getattr(config, 'sentry', {}))
    if sentry.enabled:
        sentry.init()
        sentry.bind_to_webpy_app(code.app)


def main(configfile, *args):
    setup(configfile)

    if '--archive' in args:
        archive.archive()
    else:
        sys.argv = [sys.argv[0]] + list(args)
        code.app.run()


if __name__ == "__main__":
    main(*sys.argv[1:])
