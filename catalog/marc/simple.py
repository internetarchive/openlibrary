#!/usr/bin/python2.5
from catalog.get_ia import *
from catalog.read_rc import read_rc
from catalog.marc.fast_parse import get_all_tag_lines, get_all_subfields
import sys

rc = read_rc()
marc_path = rc['marc_path']
full_part = sys.argv[1]

show_non_books = False

# simple parse of a MARC binary, just counts types of items

total, sound_rec, not_book, book = 0, 0, 0, 0
for pos, loc, data in read_marc_file(full_part, open(marc_path + full_part)):
    total += 1
    try:
        rec = fast_parse.read_edition(data)
    except fast_parse.SoundRecording:
        sound_rec += 1
        continue
    if not rec:
        if show_non_books:
            print data[:24]
            for tag, line in get_all_tag_lines(data):
                print tag, list(get_all_subfields(line))
            print
        not_book += 1
    else:
        book += 1

print "total records:", total
print "sound recordings:", sound_rec
print "not books:", not_book
print "books:", book
