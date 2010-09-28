#!/usr/bin/python2.5
# converts from text files containing MARC tags to text versions of merge pools

import re, anydbm
from time import time
from collections import defaultdict

grand_total = 31388611

archive = [
    ('marc_western_washington_univ', 'Western Washington University', 737442),
    ('marc_records_scriblio_net', 'Library of Congress', 7025345),
    ('marc_university_of_toronto', 'University of Toronto', 5585777),
    ('marc_miami_univ_ohio', 'Miami University', 2029148),
    ('bcl_marc', 'Boston College', 1983155),
    ('bpl_marc', 'Boston Public Library', 2165372),
    ('unc_catalog_marc', 'University of North Carolina at Chapel Hill', 3738594),
    ('marc_oregon_summit_records', 'Oregon Summit', 3275046),
    ('talis_openlibrary_contribution', 'Talis', 4848732),
]

path = '/0/pharos/edward/db/'

re_isbn = re.compile('([^ ()]+[\dX])(?: \((?:v\. (\d+)(?: : )?)?(.*)\))?')
re_question = re.compile('^\?+$')
re_lccn = re.compile('(...\d+).*')
re_oclc = re.compile ('^\(OCoLC\).*?0*(\d+)', re.IGNORECASE)

re_normalize = re.compile('[^\w ]')
re_whitespace = re.compile('\s+')

def normalize(s):
    s = re_normalize.sub('', s.strip())
    s = re_whitespace.sub(' ', s)
    return s.lower()

def add_to_map(d, k, loc):
    d[k].append(loc)

def add_title_to_map(title, loc):
    title = str(normalize(title)[:25])
    add_to_map(title_map, title, loc)

def add_title(prefix_len, subtags):
    title_and_subtitle = []
    title = []
    for k, v in subtags:
        if k not in ('a', 'b'):
            continue
        v = v.strip(' /,;:')
        title_and_subtitle.append(v)
        if k == 'a':
            title.append(v)
    
    titles = [' '.join(title)]
    if title != title_and_subtitle:
        titles.append(' '.join(title_and_subtitle))
    if prefix_len and prefix_len != '0':
        try:
            prefix_len = int(prefix_len)
            titles += [t[prefix_len:] for t in titles]
        except ValueError:
            pass
    return titles

loc_num = 0

def write_map(archive_id, name, d):
    f = open('d/' + archive_id + '_' + name, 'w')
    for k, v in d.iteritems():
        f.write(k + '\t' + ' '.join([str(i) for i in v]) + '\n')
    f.close()

def add_record(edition):
    global loc_num
    loc_str, tags = edition
    loc_num+=1
    f_loc.write(str(loc_num) + ' ' + loc_str + '\n')
    loc = loc_num
    for tag, ind, subtags in tags:
        if tag == '010':
            for k, v in subtags:
                lccn = v.strip()
                if re_question.match(lccn):
                    continue
                m = re_lccn.search(lccn)
                if m:
                    add_to_map(lccn_map, m.group(1), loc)
            continue
        if tag == '020':
            for k, v in subtags:
                m = re_isbn.match(v)
                if m:
                    add_to_map(isbn_map, m.group(1), loc)
            continue
        if tag == '035':
            for k, v in subtags:
                m = re_oclc.match(v)
                if m:
                    add_to_map(oclc_map, m.group(1), loc)
            continue
        if tag == '245':
            for t in add_title(ind[1], subtags):
                add_title_to_map(t, loc)
            continue

overall = 0
t0_overall = time()
f_loc = open('d/loc_map', 'w')
for archive_id, name, total in sorted(archive, key=lambda x: x[2]):
    t0 = time()
    i = 0

    isbn_map = defaultdict(list)
    lccn_map = defaultdict(list)
    title_map = defaultdict(list)
    oclc_map = defaultdict(list)
    print archive_id
    for line in open(archive_id):
        rec = eval(line)
        add_record(rec)
        i+=1
        overall+=1
        if i % 10000 == 0:
            t1 = time() - t0
            t1_overall = time() - t0_overall
            remaining = total - i
            remaining2 = grand_total - overall
            print "%8d %6.2f%% %5.3f rec/sec %.3f minutes left" % (i, (float(i) * 100) / total, i/t1, float((t1/i) * remaining) / 60),
            print "overall: %6.2f%% %.3f minutes left" % ((float(overall) * 100) / grand_total, float((t1_overall/overall) * remaining2) / 60)

    print archive_id
    write_map(archive_id, 'isbn', isbn_map)
    write_map(archive_id, 'lccn', lccn_map)
    write_map(archive_id, 'title', title_map)
    write_map(archive_id, 'oclc', oclc_map)

f_loc.close()
print 'end'
