import re, sys
import xml.etree.ElementTree as et
from pprint import pprint

def parse_catrecord(catrecord):
    record = {}
    re_bad_tag = re.compile(r'(<[^>]*?\s[^>]*?>)')
    re_white = re.compile(r'\s')
    catrecord = re_bad_tag.sub(lambda m: re_white.sub('', m.group(1)), catrecord)
    tree = et.fromstring(catrecord)
    record = {}
    for e in tree:
        f = e.tag.lower()
        if e.tag == 'AUTHORS':
            assert f not in record
            record[f] = [(a.tag.lower(), a.text) for a in e]
            continue
        if e.tag == 'SEGMENT':
            d = dict([(a.tag.lower(), a.text) for a in e])
            record.setdefault(f, []).append(d)
            continue
        elif e.tag in ('SUBJ', 'COLL', 'ALTTI', 'SERIES'):
            record.setdefault(f, []).append(e.text)
            continue
        assert len(e) == 0
        assert f not in record
        record[f] = e.text
    return record

def parse_file():
    cur = ''
    expect = 'start'
    i = 0
    re_call = re.compile('^<CALL>(.*)</CALL>\r\n$')
    re_itemid = re.compile('^<ITEMID>(.*)</ITEMID>\r\n$')
    for line in open(sys.argv[1]):
        i+=1
        assert expect != 'end_file'
        if expect == 'start':
            assert line == '<LIBRARY>Department of Treasury\r\n'
            expect = 'start_catrecord'
            continue
        if expect == 'start_catrecord':
            if line == '</CATRECORD>\r\n':
                print "skipping duplicate CATRECORD"
                continue
            assert line == '<CATRECORD>\r\n'
            cur += line
            expect = 'end_catrecord'
            continue
        if expect == 'end_catrecord': 
            if line.startswith('</CATRECORD>'):
                cur += '</CATRECORD>'
                yield parse_catrecord(cur)

                cur = ''
                if line == '</CATRECORD></LIBRARY>\r\n':
                    expect = 'end_file'
                else:
                    assert line == '</CATRECORD>\r\n'
                    expect = 'start_catrecord'
                continue
            else:
                cur += line

    assert expect == 'end_file'

for rec in parse_file():
    pprint(rec)
