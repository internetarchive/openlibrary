#!/usr/bin/env python
"""
Temporary script to store unique IPs in a single day by parsing the
lighttpd log files directly.
"""
import os
import datetime
import subprocess


def run_for_day(d):
    basedir = "/var/log/lighttpd/%(year)d/%(month)d/%(day)d/"%dict(year = d.year, month = d.month, day = d.day)
    counter = ["|", "awk '$2 == \"openlibrary.org\" { print $1  }'", "|", "sort -u", "|", "wc -l"]
    if os.path.exists(basedir + "access.log.gz"):
        cmd = ["zcat %s/access.log.gz"%basedir ] + counter
    elif os.path.exists(basedir + "access.log"):
        cmd = ["cat %s/access.log"%basedir] + counter
    p = subprocess.Popen(cmd, stdout = subprocess.PIPE, shell = True)
    p.wait()
    val = p.stdout.read()
    return val
    
def main():
    current = datetime.datetime.now()
    for i in range(10):
        print current
        print run_for_day(current)
        current = current - datetime.timedelta(days = 1)

if __name__ == "__main__":
    import sys
    sys.exit(main())




