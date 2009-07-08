# build a merge database from JSON dump

import simplejson, re
from normalize import normalize
from time import time

re_escape = re.compile(r'[\n\r\t\0\\]')
trans = { '\n': '\\n', '\r': '\\r', '\t': '\\t', '\\': '\\\\', '\0': '', }

def esc_group(m):
    return trans[m.group(0)]
def esc(str): return re_escape.sub(esc_group, str)

def add_to_index(fh, value, key):
    if not value:
        return
    try:
        value = str(value)
    except UnicodeEncodeError:
        return
    print >> fh, "\t".join([key, esc(value)])

def short_title(s):
    return normalize(s)[:25]

re_letters = re.compile('[A-Za-z]')
re_dash_or_space = re.compile('[- ]')

def clean_lccn(lccn):
    return re_letters.sub('', lccn).strip()

def clean_isbn(isbn):
    return re_dash_or_space.sub('', isbn)

def load_record(record, f):
    if 'title' not in record or record['title'] is None:
        return
    if 'subtitle' in record and record['subtitle'] is not None:
        title = record['title'] + ' ' + record['subtitle']
    else:
        title = record['title']
    key = record['key']
    add_to_index(f['title'], short_title(title), key)
    if 'title_prefix' in record and record['title_prefix'] is not None:
        title2 = short_title(record['title_prefix'] + title)
        add_to_index(f['title'], title2, key)

    fields = [
        ('lccn', 'lccn', clean_lccn),
        ('oclc_numbers', 'oclc', None),
        ('isbn_10', 'isbn', clean_isbn),
        ('isbn_13', 'isbn', clean_isbn),
    ]
    for a, b, clean in fields:
        if a not in record:
            continue
        for v in record[a]:
            if not v or b=='isbn' and len(v) < 10:
                continue
            if clean:
                v = clean(v)
            add_to_index(f[b], v, key)

total = 29107946 # FIXME

path = '/1/edward/index/'
index_fields = ('lccn', 'oclc', 'isbn', 'title')
files = dict((i, open(path + i, 'w')) for i in index_fields)

rec_no = 0
chunk = 10000
t0 = time()
t_prev = time()

filename = '/1/anand/bsddb/json.txt'
for line in open(filename):
    rec_no += 1

    if rec_no % chunk == 0:
        t = time() - t_prev
        t_prev = time()
        t1 = time() - t0
        rec_per_sec = chunk / t
        rec_per_sec_total = rec_no / t1
        remaining = total - rec_no
        sec = remaining / rec_per_sec_total
        print "%d current: %.3f overall: %.3f" % \
            (rec_no, rec_per_sec, rec_per_sec_total),
        mins = sec / 60
        print "%.3f minutes left" % mins

    # split line
    key, type, json_data = line.split('\t')
    if type != '/type/edition':
        continue
    try:
        rec = simplejson.loads(json_data)
        load_record(rec, files)
    except:
        print 'record number:', rec_no
        print line
        raise

print rec_no
print "closing files"
for v in files.values():
    v.close()
print "finished"
