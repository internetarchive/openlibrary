#!/usr/bin/python2.5
from catalog.marc.fast_parse import *
import sys

# read a MARC binary showing one record at a time

for data, length in read_file(open(sys.argv[1])):
    print data[:24]
    for tag, line in get_all_tag_lines(data):
        if tag.startswith('00'):
            print tag, line[:-1]
        else:
            print tag, list(get_all_subfields(line))
    print
