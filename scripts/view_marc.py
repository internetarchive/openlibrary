#!/usr/bin/python2.5
from openlibrary.catalog.marc.fast_parse import *
from openlibrary.catalog.get_ia import get_from_archive
import sys, codecs, re

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

re_subtag = re.compile('\x1f(.)([^\x1f]*)')

def fmt_subfields(line):
    def bold(s):
        return ''.join(c + "\b" + c for c in s)
    assert line[-1] == '\x1e'
    return ''.join(' ' + bold('$' + m.group(1)) + ' ' + translate(m.group(2)) for m in re_subtag.finditer(line[2:-1]))

def show_book(data):
    print 'leader:', data[:24]
    for tag, line in get_all_tag_lines(data):
        if tag.startswith('00'):
            print tag, line[:-1]
        else:
            print tag, line[0:2], fmt_subfields(line)

if __name__ == '__main__':
    source = sys.argv[1]
    if ':' in source:
        data = get_from_archive(source)
    else:
        data = open(source).read()
    show_book(data)
