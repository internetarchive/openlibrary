"""Noticed some duplicate entries in the thing table of OL database.
There should have been a unique constrant on thing.key, but that was missing. 
Quick analysis revealed that there are many work records with single dup and the dup has only one revision.

This script removes those dups.
"""
import web
import os
import simplejson
from collections import defaultdict

db = web.database(dbn="postgres", db="openlibrary", user=os.getenv("USER"), pw="")

def get_json(thing_id, revision):
    json = db.where('data', thing_id=thing_id, revision=revision)[0].data
    d = simplejson.loads(json)
    del d['created']
    del d['last_modified']
    return d

def fix_work_dup(key):
    rows = db.where("thing", key=key).list()
    if len(rows) == 1:
        print key, "already fixed"
        return 
    elif len(rows) == 2:
        w1, w2 = rows
        if w1.latest_revision < w2.latest_revision:
            w1, w2 = w2, w1
        print key, "fixing single dup", w1.id, w1.latest_revision, w2.id, w2.latest_revision
        if w2.latest_revision == 1 and get_json(w1.id, 1) == get_json(w2.id, 1):
            print "RENAME", w2.id, w2.key + "--dup"
    else:
        print key, "many dups"

@web.memoize
def get_property_id(type, name):
    type_id = db.where("thing", key=type)[0].id
    return db.where("property", type=type_id, name=name)[0].id

def find_edition_count(thing_ids):
    key_id = get_property_id("/type/edition", "works")
    rows = db.query("SELECT * FROM edition_ref WHERE key_id=$key_id AND value IN $thing_ids", vars=locals())

    d = defaultdict(lambda: 0)
    for row in rows:
        d[row.thing_id] += 1
    return d

def get_data(thing_ids):
    rows = db.query("SELECT * FROM data WHERE thing_id IN $thing_ids and revision=1", vars=locals())
    d = {}
    for row in rows:
        data = simplejson.loads(row.data)
        del data['created']
        del data['last_modified']
        d[row.thing_id] = data
    return d

def find_more_info(key):
    rows = db.where("thing", key=key).list()
    for row in rows:
        editions = db.where("edition_ref", key_id=get_property_id("/type/edition", "works"), value=row.id)
        row.edition_count = len(editions)
        row.data = get_json(row.id, 1)
        row.created = row.created.isoformat()
        row.last_modified = row.last_modified.isoformat()

    print key, simplejson.dumps(rows)

def main(dups_file):
    keys = [key.strip() for key in open(dups_file) if key.startswith("/works/")]
    for key in keys:
        find_more_info(key)

def generate_tsv(jsonfile):
    for line in open(jsonfile):
        key, json = line.strip().split(None, 1)
        works = simplejson.loads(json)
        for w in sorted(works, key=lambda w: w['latest_revision'], reverse=True):
            cols = key, w['id'], w['latest_revision'], w['edition_count'], w['data']['title'], ",".join(a['author']['key'] for a in w['data']['authors'])
            print "\t".join(web.safestr(c) for c in cols)

if __name__ == "__main__":
    import sys
    #main(sys.argv[1])
    generate_tsv(sys.argv[1])

