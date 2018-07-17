#!/olsystem/bin/olenv python
"""
Temporary script to store unique IPs in a single day by parsing the
lighttpd log files directly.
"""
import _init_path
import os
import datetime
import subprocess
import web
import infogami

def store_data(data, date):
    uid = date.strftime("counts-%Y-%m-%d")

    doc = web.ctx.site.store.get(uid) or {}
    doc.update(data)
    doc['type'] = 'admin-stats'
    web.ctx.site.store[uid] = doc


def run_for_day(d):
    basedir = d.strftime("/var/log/nginx/")
    awk = ["awk", '$2 == "openlibrary.org" { print $1 }']
    sort = ["sort", "-u"]
    count = ["wc", "-l"]
    print "           ", basedir
    zipfile = d.strftime("access.log-%Y%m%d.gz")
    if os.path.exists(basedir + zipfile):
        print "              Using ",  basedir + zipfile
        cmd = subprocess.Popen(["zcat", basedir + zipfile], stdout = subprocess.PIPE)
    elif os.path.exists(basedir + "access.log"):
        cmd = subprocess.Popen(["cat", "%s/access.log"%basedir], stdout = subprocess.PIPE)
        print "              Using ",  basedir + "access.log"
    print "           ", awk
    cmd = subprocess.Popen(awk,   stdin = cmd.stdout, stdout = subprocess.PIPE)
    print "           ", sort
    cmd = subprocess.Popen(sort,  stdin = cmd.stdout, stdout = subprocess.PIPE)
    print "           ", count
    cmd = subprocess.Popen(count, stdin = cmd.stdout, stdout = subprocess.PIPE)
    val = cmd.stdout.read()
    return dict (visitors = int(val))


def main():
    infogami._setup()
    current = datetime.datetime.now()
    for i in range(2):
        print current
        d = run_for_day(current)
        store_data(d, current)
        current = current - datetime.timedelta(days = 1)

if __name__ == "__main__":
    import sys
    sys.exit(main())
