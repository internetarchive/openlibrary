#!/usr/bin/python2.5
from openlibrary.catalog.marc.fast_parse import *
import sys
from collections import defaultdict

# read a MARC binary showing one record at a time

field_counts = defaultdict(int)

for data, length in read_file(open(sys.argv[1])):
    print data[:24]
    is_marc8 = data[9] != 'a'
    for tag, line in get_all_tag_lines(data):
        if tag.startswith('00'):
            print tag, line[:-1]
        else:
            print tag, list(get_all_subfields(line, is_marc8))
        field_counts[tag] += 1
    print
    print dict(field_counts)
    print
