#!/usr/bin/python2.5
from catalog.marc.fast_parse import *
from catalog.read_rc import read_rc
from catalog.get_ia import files
from sources import sources
import sys, os

rc = read_rc()
read_count = 10000

show_bad_records = False

for ia, name in sources(): # find which sources include '001' tag
    has_001 = 0
    rec_no = 0
    for part, size in files(ia):
        filename = rc['marc_path'] + ia + "/" + part
        if not os.path.exists(filename):
            continue
        for data, length in read_file(open(filename)):
            if rec_no == read_count:
                break
            rec_no += 1
            if list(get_tag_lines(data, ['001'])):
                has_001 += 1
            elif show_bad_records:
                print data[:24]
                for tag, line in get_all_tag_lines(data):
                    if tag.startswith('00'):
                        print tag, line[:-1]
                    else:
                        print tag, list(get_all_subfields(line))
        if rec_no == read_count:
            break
    print "%5d %s %s" % (has_001, ia, name)
    continue
