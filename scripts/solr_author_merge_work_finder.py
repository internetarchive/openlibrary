#!/usr/bin/python

import _init_path

from openlibrary import config
import argparse, simplejson, re
from urllib import urlopen
from time import time, sleep
from openlibrary.catalog.works.find_works import find_title_redirects, find_works, get_books, books_query, update_works

parser = argparse.ArgumentParser(description='solr author merge')
parser.add_argument('--config', default='openlibrary.yml')
parser.add_argument('--state_file', default='author_merge_work_finder')
args = parser.parse_args()

config_file = args.config
config.load(config_file)

update_times = []

state_file = config.runtime_config['state_dir'] + '/' + args.state_file
offset = open(state_file).readline()[:-1]

base = 'http://%s/openlibrary.org/log/' % config.runtime_config['infobase_server']

def run_work_finder(i):
    t0 = time()
    d = i['data']
    print 'timestamp:', i['timestamp']
    print 'author:', d['author']
    print '%d records updated:' % len(d['result'])
    if 'changeset' not in d:
        print 'no changeset in author merge'
        print
        return
    changeset = d['changeset']

    try:
        assert len(changeset['data']) == 2 and 'master' in changeset['data'] and 'duplicates' in changeset['data']
    except:
        print d['changeset']
        raise
    akey = changeset['data']['master']
    dup_keys = changeset['data']['duplicates']
    #print d['changeset']
    print 'dups:', dup_keys

    title_redirects = find_title_redirects(akey)
    works = find_works(get_books(akey, books_query(akey)), existing=title_redirects)
    print 'author:', akey
    print 'works:', works
    updated = update_works(akey, works, do_updates=True)
    print '%d records updated' % len(updated)

    t1 = time() - t0
    update_times.append(t1)
    print 'update takes: %d seconds' % t1
    print

while True:
    url = base + offset
    print url,

    try:
        data = urlopen(url).read()
    except URLError as inst:
        if inst.args and inst.args[0].args == (111, 'Connection refused'):
            print 'make sure infogami server is working, connection refused from:'
            print url
            sys.exit(0)
        print 'url:', url
        raise
    try:
        ret = simplejson.loads(data)
    except:
        open('bad_data.json', 'w').write(data)
        raise

    offset = ret['offset']
    data_list = ret['data']
    if len(data_list) == 0:
        print 'waiting'
        sleep(10)
        continue
    else:
        print
    for i in data_list:
        action = i.pop('action')
        if action != 'save_many':
            continue
        if i['data']['changeset']['kind'] != 'merge-authors':
            continue
        if len(i['data']['result']) == 0:
            continue # no change
        print 'run work finder'
        try:
            run_work_finder(i)
        except:
            print offset
            raise

        if update_times:
            print "average update time: %.1f seconds" % (float(sum(update_times)) / float(len(update_times)))
    print >> open(state_file, 'w'), offset

