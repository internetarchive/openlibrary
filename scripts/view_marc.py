#!/usr/bin/python3

from __future__ import print_function

import codecs
import re
import sys

import _init_path
from openlibrary.catalog.get_ia import get_from_archive
from openlibrary.catalog.marc.fast_parse import get_all_tag_lines, translate

if bytes == str:  # PY2
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

re_subtag = re.compile('\x1f(.)([^\x1f]*)')

def fmt_subfields(line):
    def bold(s):
        return ''.join(c + "\b" + c for c in s)
    assert line[-1] == '\x1e'
    return ''.join(' ' + bold('$' + m.group(1)) + ' ' + translate(m.group(2)) for m in re_subtag.finditer(line[2:-1]))

def show_book(data):
    print('leader:', data[:24])
    for tag, line in get_all_tag_lines(data):
        if tag.startswith('00'):
            print(tag, line[:-1])
        else:
            print(tag, line[0:2], fmt_subfields(line))

if __name__ == '__main__':
    SAMPLE = ("openlibrary/catalog/marc/tests/test_data/bin_input/"
              "0descriptionofta1682unit_meta.mrc")
    sources = sys.argv[1:] or [SAMPLE]
    for source in sources:
        if ':' in source:
            data = get_from_archive(source)
        else:
            data = open(source).read()
        show_book(data)
