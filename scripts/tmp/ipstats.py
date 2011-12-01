#!/olsystem/bin/olenv python
"""
Temporary script to store unique IPs in a single day by parsing the
lighttpd log files directly.
"""
import os
import datetime
import subprocess

import couchdb
import yaml

def connect_to_couch(config_file):
    "Connects to the couch databases"
    f = open(config_file)
    config = yaml.load(f)
    f.close()
    admin_db = config["admin"]["counts_db"]
    return couchdb.Database(admin_db)

def store_data(db, data, date):
    uid = date.strftime("counts-%Y-%m-%d")
    print uid
    try:
        vals = db[uid]
        vals.update(data)
    except couchdb.http.ResourceNotFound:
        vals = data
        db[uid] = vals
    print "saving %s"%vals
    db.save(vals)

def run_for_day(d):
    basedir = d.strftime("/var/log/lighttpd/%Y/%m/%d/")
    awk = ["awk", '$2 == "openlibrary.org" { print $1 }']
    sort = ["sort", "-u"]
    count = ["wc", "-l"]
    print basedir
    if os.path.exists(basedir + "access.log.gz"):
        cmd = subprocess.Popen(["zcat", "%s/access.log.gz"%basedir], stdout = subprocess.PIPE)
    elif os.path.exists(basedir + "access.log"):
        cmd = subprocess.Popen(["cat", "%s/access.log"%basedir], stdout = subprocess.PIPE)
    print awk
    cmd = subprocess.Popen(awk,   stdin = cmd.stdout, stdout = subprocess.PIPE)
    print sort
    cmd = subprocess.Popen(sort,  stdin = cmd.stdout, stdout = subprocess.PIPE)
    print count
    cmd = subprocess.Popen(count, stdin = cmd.stdout, stdout = subprocess.PIPE)
    val = cmd.stdout.read()
    return dict (visitors = int(val))
    
    
def main(config):
    admin_db = connect_to_couch(config)
    current = datetime.datetime.now()
    for i in range(2):
        print current
        d = run_for_day(current)
        store_data(admin_db, d, current)
        current = current - datetime.timedelta(days = 1)

if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1]))






