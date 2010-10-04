#!/usr/bin/python2.5
from openlibrary.catalog.marc.fast_parse import *
from openlibrary.catalog.get_ia import get_from_archive
import sys, codecs, re

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

re_subtag = re.compile('\x1f[^\x1b]')

def fmt_subfields(line, is_marc8=False):
    def bold(s):
        return ''.join(c + "\b" + c for c in s)
    assert line[-1] == '\x1e'

    encode = {
        'k': lambda s: bold('$%s' % s),
        'v': lambda s: translate(s, leader_says_marc8=marc8),
    }
    return ''.join(encode[k](v) for k, v in split_line(line[2:-1]))
    pos = 0
    prev = None
    subfields = []
    for m in re_subtag.finditer(line[2:-1]):
        if prev is None:
            prev = m.start()
            continue
        subfields.append(line[prev+3:m.start()+2])
        prev = m.start()
    subfields.append(line[prev+3:-1])

    return ''.join(' ' + bold('$' + i[0]) + ' ' + (translate(i[1:], leader_says_marc8=leader_says_marc8) if i else '') for i in subfields)

def show_book(data):
    is_marc8 = data[9] == ' '
    print 'leader:', data[:24]
    for tag, line in get_all_tag_lines(data):
        print tag, `line`
        continue
        if tag.startswith('00'):
            print tag, line[:-1]
        else:
            print tag, line[0:2], fmt_subfields(line, is_marc8=is_marc8)

if __name__ == '__main__':
    source = sys.argv[1]
    if ':' in source:
        data = get_from_archive(source)
    else:
        data = open(source).read()
    show_book(data)
