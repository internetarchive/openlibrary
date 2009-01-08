from catalog.infostore import get_site
from catalog.read_rc import read_rc
import web, sys, codecs, os.path, re
from pprint import pprint
from catalog.olwrite import Infogami
site = get_site()

import psycopg2
rc = read_rc()
infogami = Infogami(rc['infogami'])
infogami.login('EdwardBot', rc['EdwardBot'])

re_marc_name = re.compile('^(.*), (.*)$')
re_end_dot = re.compile('[^ ][^ ]\.$', re.UNICODE)

out = open('author_replace3', 'w')

# find books with matching ISBN and fix them to use better author record

def flip_name(name):
    # strip end dots like this: "Smith, John." but not like this: "Smith, J."
    m = re_end_dot.search(name)
    if m:
        name = name[:-1]

    m = re_marc_name.match(name)
    return m.group(2) + ' ' + m.group(1)

conn = psycopg2.connect("dbname='%s' user='%s' host='%s' password='%s'" \
        % ('ol_merge', rc['user'], rc['host'], rc['pw']));
cur = conn.cursor()

author_fields = ('key', 'name', 'title', 'birth_date', 'death_date', 'personal_name')

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
for line in open('dups'):
    isbn, num = eval(line)
    if isbn < '0273314165':
        continue
    cur.execute('select key from isbn where value=%(v)s', {'v':isbn})
    found = []
    names = {}
    for i in cur.fetchall():
        key = i[0]
        e = site.withKey(key)
        author_list = e.authors or []
        authors = [dict(((k, v) for k, v in a._get_data().items() if k in author_fields)) for a in author_list if a]
        for a in authors:
            if 'name' not in a:
                continue
            name = a['name']
            if name.find(', ') != -1:
                name = flip_name(name)
            a2 = a.copy()
            a2['edition'] = key
            names.setdefault(name, []).append(a2)
        found.append((key, authors))
    if len([1 for k, a in found if a]) < 2:
        continue
    if not any(any('birth_date' in j or 'death_date' in j for j in i[1]) for i in found):
        continue
    names = dict((k, v) for k, v in names.iteritems() if len(set(i['key'] for i in v)) > 1)
    if not names:
        continue
    author_replace = {}
    for name, authors in names.items():
        seen = set()
#        print 'birth:', [a['birth_date'].strip('.') for a in authors if 'birth_date' in a]
#        print 'death:', [a['death_date'].strip('.') for a in authors if 'death_date' in a]
        with_dates = None
        no_dates = []
        for a in authors:
            if a['key'] in seen:
                continue
            seen.add(a['key'])
            if 'birth_date' in a or 'death_date' in a:
                if with_dates:
                    with_dates = None
                    break
                with_dates = a['key']
                continue
            no_dates.append(a['key'])
        if with_dates and no_dates:
            for i in no_dates:
                assert i not in author_replace
                author_replace[i] = with_dates
    if not author_replace:
        continue
    print isbn, author_replace
#    pprint(names)
    for key, authors in found:
        replace = [a['key'] for a in authors if a['key'] in author_replace]
        if len(replace) == 0:
            continue
#        print len(replace), key, [a['key'] for a in authors]
        new_authors = []
        this = {}
        for a in authors:
            akey = a['key']
            if akey in author_replace:
                this[akey] = author_replace[akey]
                akey = author_replace[akey]
            if akey not in new_authors:
                new_authors.append(akey)
        q = {
            'key': key,
            'authors': { 'connect': 'update_list', 'value': new_authors }
        }
        print >> out, (key, this)
#    for k in author_replace.keys():
#        print k, len(site.things({'type': '/type/edition', 'authors': k}))
            
#    pprint(found)
#    for name, v in names.items():
#        print name
#        for edition, author in v:
#            print author, site.things({'type': '/type/edition', 'authors': author})
#    print
out.close()
