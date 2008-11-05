#!/usr/bin/python2.5
from catalog.read_rc import read_rc
from catalog.marc.fast_parse import *
import sys

show_non_books = False

# simple parse of a MARC binary, just counts types of items

total, sound_rec, not_book, book = 0, 0, 0, 0
for data, length in read_file(open(sys.argv[1])):
    total += 1
    try:
        rec = read_edition(data)
    except SoundRecording:
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
