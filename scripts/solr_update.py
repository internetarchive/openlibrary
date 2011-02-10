#!/usr/bin/env python

import _init_path

from urllib import urlopen
import simplejson, re
from time import time, sleep
from openlibrary.catalog.utils.query import withKey, set_query_host
from openlibrary.solr.update import subject_count, subject_need_update
from openlibrary.solr.update_work import update_work, solr_update, update_author, AuthorRedirect, get_work_subjects, add_field, strip_bad_char
from lxml.etree import tostring, Element
from openlibrary.api import OpenLibrary, Reference
from openlibrary.catalog.read_rc import read_rc
from openlibrary import config
import argparse
from os.path import exists
import sys

parser = argparse.ArgumentParser(description='update solr')
parser.add_argument('--server', default='openlibrary.org')
parser.add_argument('--config', default='openlibrary.yml')
parser.add_argument('--author_limit', default=1000)
parser.add_argument('--work_limit', default=1000)
parser.add_argument('--skip_user', action='append', default=[])
parser.add_argument('--only_user', action='append', default=[])
parser.add_argument('--state_file', default='solr_update')
parser.add_argument('--handle_author_merge', action='store_true')
parser.add_argument('--mins', default=5)
parser.add_argument('--only_author_merge', action='store_true')
parser.add_argument('--skip_author_merge', action='store_true')
parser.add_argument('--no_commit', action='store_true')
parser.add_argument('--no_author_updates', action='store_true')
parser.add_argument('--just_consider_authors', action='store_true')
parser.add_argument('--limit', default=None)

args = parser.parse_args()
handle_author_merge = args.handle_author_merge
only_author_merge = args.only_author_merge
skip_author_merge = args.skip_author_merge

if only_author_merge:
    handle_author_merge = True

if handle_author_merge:
    from openlibrary.catalog.works.find_works import find_title_redirects, find_works, get_books, books_query, update_works

ol = OpenLibrary("http://" + args.server)
set_query_host(args.server)
done_login = False

config_file = args.config
config.load(config_file)

solr_works = config.runtime_config["plugin_worksearch"]["solr"]
solr_subjects = config.runtime_config["plugin_worksearch"]["subject_solr"]

base = 'http://%s/openlibrary.org/log/' % config.runtime_config['infobase_server']

skip_user = set(u.lower() for u in args.skip_user)
only_user = set(u.lower() for u in args.only_user)

if 'state_dir' not in config.runtime_config:
    print 'state_dir missing from ' + config_file
    sys.exit(0)

state_file = config.runtime_config['state_dir'] + '/' + args.state_file

if exists(state_file):
    offset = open(state_file).readline()[:-1]
else:
    offset = "2010-06-01:0"

print 'start:', offset
authors_to_update = set()
works_to_update = set()
last_update = time()
author_limit = int(args.author_limit)
work_limit = int(args.work_limit)
time_limit = 60 * int(args.mins)

def run_update():
    global authors_to_update, works_to_update
    subjects_to_update = set()
    global last_update
    print 'running update: %s works %s authors' % (len(works_to_update), len(authors_to_update))
    if works_to_update:
        requests = []
        num = 0
        total = len(works_to_update)
        for wkey in works_to_update:
            num += 1
            print 'update work: %s %d/%d' % (wkey, num, total)
            if '/' in wkey[7:]:
                print 'bad wkey:', wkey
                continue
            work_to_update = withKey(wkey)
            for attempt in range(5):
                try:
                    requests += update_work(work_to_update)
                except AuthorRedirect:
                    print 'fixing author redirect'
                    w = ol.get(wkey)
                    need_update = False
                    for a in w['authors']:
                        r = ol.get(a['author'])
                        if r['type'] == '/type/redirect':
                            a['author'] = {'key': r['location']}
                            need_update = True
                    if need_update:
                        if not done_login:
                            rc = read_rc()
                            ol.login('EdwardBot', rc['EdwardBot']) 
                        ol.save(w['key'], w, 'avoid author redirect')
            if work_to_update['type']['key'] == '/type/work' and work_to_update.get('title'):
                subjects = get_work_subjects(work_to_update)
                print subjects
                for subject_type, values in subjects.iteritems():
                    subjects_to_update.update((subject_type, v) for v in values)
                if len(requests) >= 100:
                    solr_update(requests, debug=True)
                    requests = []
    #            if num % 1000 == 0:
    #                solr_update(['<commit/>'], debug=True)
        if requests:
            solr_update(requests, debug=True)
        if not args.no_commit:
            solr_update(['<commit/>'], debug=True)
    last_update = time()
    if not args.no_author_updates and authors_to_update:
        requests = []
        for akey in authors_to_update:
            print 'update author:', `akey`
            requests += update_author(akey)
        if not args.no_commit:
            solr_update(requests + ['<commit/>'], index='authors', debug=True)
    subject_add = Element("add")
    print subjects_to_update
    for subject_type, subject_name in subjects_to_update:
        key = subject_type + '/' + subject_name
        count = subject_count(subject_type, subject_name)

        if not subject_need_update(key, count):
            print 'no updated needed:', (subject_type, subject_name, count)
            continue
        print 'updated needed:', (subject_type, subject_name, count)

        doc = Element("doc")
        add_field(doc, 'key', key)
        add_field(doc, 'name', subject_name)
        add_field(doc, 'type', subject_type)
        add_field(doc, 'count', count)
        subject_add.append(doc)

    if len(subject_add):
        print 'updating subjects'
        add_xml = tostring(subject_add).encode('utf-8')
        solr_update([add_xml, '<commit />'], debug=True, index='subjects')

    authors_to_update = set()
    works_to_update = set()
    subjects_to_update = set()
    print >> open(state_file, 'w'), offset

def process_save(key, query):
    if query:
        obj_type = query['type']['key'] if isinstance(query['type'], dict) else query['type']
        if obj_type == '/type/delete':
            print key, 'deleted'
    if key.startswith('/authors/') or key.startswith('/a/'):
        authors_to_update.add(key)
        q = {
            'type':'/type/work',
            'authors':{'author':{'key': key}},
            'limit':0,
        }
        works = None
        for attempt in range(5):
            try:
                works = ol.query(q)
                break
            except:
                sleep(10)
        if not works:
            works = ol.query(q)
        works_to_update.update(works)
        return
    elif args.just_consider_authors:
        return
    if key.startswith('/works/'):
        works_to_update.add(key)

        authors = [a['author']['key'] if isinstance(a['author'], dict) else a['author'] for a in (query.get('authors') or []) if a.get('author')]
        if query:
            authors_to_update.update(a for a in authors if a)
        return
    if (key.startswith('/books/') or key.startswith('/b/')) and query and obj_type != '/type/delete':
        if obj_type != '/type/edition':
            print 'bad type for ', key
            return
        works_to_update.update(w['key'] if isinstance(w, dict) else w for w in (query.get('works') or []))
        try:
            authors_to_update.update(a['key'] if isinstance(a, dict) else a for a in (query.get('authors') or []))
        except:
            print query
            raise

while True:
    url = base + offset
    if args.limit:
        url += '?limit=' + args.limit
    print url
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
    data = ret['data']
    print offset, len(data), '%s works %s authors' % (len(works_to_update), len(authors_to_update))
    if len(data) == 0:
        if authors_to_update or works_to_update:
            run_update()
        sleep(5)
        continue
    for i in data:
        action = i.pop('action')
        if action == 'new_account':
            continue
        author = i['data'].get('author') if 'data' in i else None
        lc_author = None
        if author:
            author = author.split('/')[-1]
            lc_author = author.lower()
            if lc_author in skip_user or (only_user and lc_author not in only_user):
                continue
        if author == 'AccountBot':
            if action not in ('save', 'save_many'):
                print action, author, key, i.keys()
                print i['data']
            assert action in ('save', 'save_many')
            continue
        if action == 'save':
            if only_author_merge:
                continue
            key = i['data'].pop('key')
            process_save(key, i['data']['query'])
        elif action == 'save_many':
            author_merge = i['data']['comment'] == 'merge authors'
            if author_merge and skip_author_merge:
                continue
            if author_merge and only_author_merge:
                continue
            if handle_author_merge and not i['data']['author'].endswith('Bot') and author_merge:
                first_redirect = i['data']['query'][0]
                assert first_redirect['type']['key'] == '/type/redirect'
                akey = first_redirect['location']
                if akey.startswith('/authors/'):
                    akey = '/a/' + akey[len('/authors/'):]
                title_redirects = find_title_redirects(akey)
                works = find_works(akey, get_books(akey, books_query(akey)), existing=title_redirects)
                updated = update_works(akey, works, do_updates=True)
                works_to_update.update(w['key'] for w in updated)
            for query in i['data']['query']:
                key = query.pop('key')
                process_save(key, query)
    since_last_update = time() - last_update
    if len(works_to_update) > work_limit or len(authors_to_update) > author_limit or since_last_update > time_limit:
        run_update()
