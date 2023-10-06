import re
import json
import sys
from time import time
import web

re_author_key = re.compile(r'^/a/OL(\d+)A$')
re_work_key = re.compile(r'^/works/OL(\d+)W$')
re_edition_key = re.compile(r'^/b/OL(\d+)M$')

_escape_dict = {'\n': r'\n', '\r': r'\r', '\t': r'\t', '\\': r'\\'}


def make_sub(d):
    """
    >>> f = make_sub(dict(a='aa', bb='b'))
    >>> f('aabbb')
    'aaaabb'
    """

    def f(a):
        return d[a.group(0)]

    rx = re.compile("|".join(re.escape(key) for key in d))
    return lambda s: s and rx.sub(f, s)


def invert_dict(d):
    return {v: k for (k, v) in d.items()}


unescape = make_sub(invert_dict(_escape_dict))


def read_input():
    max_v = 0
    xdata = None
    xthing_id = None

    for line in open('data_sorted.txt'):
        thing_id, v, data = line[:-1].split('\t')
        v = int(v)
        if xthing_id and xthing_id != thing_id:
            yield unescape(xdata)
            max_v = v
            xdata = data
        elif v > max_v:
            max_v = v
            xdata = data
        xthing_id = thing_id
    yield unescape(xdata)


out_edition = open('edition_file', 'w')
out_author = open('author_file', 'w')
out_edition_work = open('edition_work_file', 'w')
out_work = open('work_file', 'w')
# 'works' and 'authors' are only used in unreachable code
works = []  # type: ignore[var-annotated]
authors = {}  # type: ignore[var-annotated]
misc_fields = [
    'created',
    'modified',
    'last_modified',
    'latest_revision',
    'personal_name',
    'id',
    'revision',
    'type',
]
rec_no = 0
t0 = time()
for data in read_input():
    rec_no += 1
    if rec_no % 100000 == 0:
        t1 = time() - t0
        print(f"{web.commify(rec_no)} {(float(t1) / 60.0):.2f} minutes")
    try:
        d = json.loads(data)
    except:
        print(data)
        raise
    t = d['type']['key']
    k = d['key']
    if t == '/type/edition':
        m = re_edition_key.match(k)
        if not m:
            print('bad edition key:', k)
            print(data)
            continue
        print(data, file=out_edition)
        for w in d.get('works', []):
            m2 = re_work_key.match(w['key'])
            if not m2:
                continue
            wkey_num = m2.group(1)
            print(wkey_num + '\t' + data, file=out_edition_work)
        continue
    if t == '/type/work':
        m = re_work_key.match(k)
        if not m:
            print('bad work key:', k)
            print(data)
            continue
        wkey_num = m.group(1)
        w = {
            'key': d['key'],
            'title': d['title'],
            'authors': [a['author']['key'] for a in d.get('authors', [])],
        }
        for f in (
            'subtitle',
            'subjects',
            'subject_places',
            'subject_times',
            'subject_people',
        ):
            if f not in d:
                continue
            w[f] = d[f]
        f = 'cover_edition'
        if f in d:
            w[f] = d[f]['key']
        #        works.append(w)
        print(w, file=out_work)
        continue
    if t == '/type/author':
        m = re_author_key.match(k)
        if not m:
            print('bad author key:', k)
            print(data)
            continue
        for f in misc_fields:
            if f in d:
                del d[f]
        print(json.dumps(d), file=out_author)
        # authors[k] = d
        continue
out_edition.close()
out_edition_work.close()
out_author.close()

print('end')
print('total records:', rec_no)

sys.exit(0)

out_work = open('work_file', 'w')
for w in works:
    m = re_work_key.match(w['key'])
    wkey_num = m.group(1)
    w['authors'] = [authors[akey] for akey in w['authors'] if (akey in authors)]
    print(wkey_num, w, file=out_work)
out_work.close()
