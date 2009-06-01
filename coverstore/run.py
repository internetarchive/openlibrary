#! /usr/bin/env python
"""Run coverstore server.

Usage:
    python run.py coverstore.yml 8080
    python run.py covestore.yml fastcgi 7070
"""

import sys
import yaml
import web

from coverstore import config, disk, code

_disks = {
    'local': disk.Disk,
    'warc': disk.WARCDisk,
    'archive': disk.ArchiveDisk
}

def make_disk(type, **kw):
    return _disks[type](**kw)

def load_config(configfile):
    d = yaml.load(open(configfile))

    for k, v in d.items():
        setattr(config, k, v)

    config.disk = disk.LayeredDisk([make_disk(**kw) for kw in d['disks']])

def main(configfile, *args):
    load_config(configfile)
    sys.argv = args
    code.run()
    
if __name__ == "__main__":
    if "--archive" in sys.argv:
        from coverstore  import archive
        web.load()
        load_config(sys.argv[1])
        archive.archive(config.disks[0], config.disks[1])
    else:
        main(*sys.argv[1:])
