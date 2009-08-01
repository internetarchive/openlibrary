#! /usr/bin/env python
"""coverstore server.
"""

import sys
import yaml

from openlibrary.coverstore import config, code, archive

def load_config(configfile):
    d = yaml.load(open(configfile))
    for k, v in d.items():
        setattr(config, k, v)

def main(configfile, *args):
    load_config(configfile)

    if '--archive' in args:
        archive.archive()
    else:
        sys.argv = [sys.argv[0]] + list(args)
        code.app.run()

if __name__ == "__main__":
    main(*sys.argv[1:])
