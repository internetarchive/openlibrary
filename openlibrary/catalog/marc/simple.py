#!/usr/bin/python2.5
from openlibrary.catalog.marc.fast_parse import *
from marc_binary import MarcBinary
import parse
#from parse import read_edition, SeeAlsoAsTitle, NoTitle
import sys, codecs, re
from getopt import getopt

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

re_subtag = re.compile('\x1f(.)([^\x1f]*)')

def fmt_subfields(line):
    def bold(s):
        return ''.join(c + "\b" + c for c in s)
    assert line[-1] == '\x1e'
    return ''.join(bold("$" + m.group(1)) + translate(m.group(2)) for m in re_subtag.finditer(line[2:-1]))

show_non_books = False
verbose = False
show_pos = False
build_rec = False
show_field = None
show_leader = True
show_leader = False

opts, files = getopt(sys.argv[1:], 'vl', ['verbose', 'show-pos', 'show-non-books', 'build-record', 'show-field='])

for o, a in opts:
    if o == '--show-pos':
        show_pos = True
    elif o == '--show-non-books':
        show_non_books = True
    elif o in ('-v', '--verbose'):
        verbose = True
    elif o == '--build-record':
        from build_record import build_record
        from pprint import pprint
        build_rec = True
    elif o == '--show-field':
        show_field = a
    elif o == '-l':
        show_leader = True

# simple parse of a MARC binary, just counts types of items

def show_book(data):
    print 'leader:', data[:24]
    for tag, line in get_all_tag_lines(data):
        if tag.startswith('00'):
            print tag, line[:-1]
        else:
            print tag, line[0:2], fmt_subfields(line)

total, bad_dict, sound_rec, not_book, book = 0, 0, 0, 0, 0
f = open(files[0])
next = 0
for data, length in read_file(f):
    pos = next
    next += length
    total += 1
    if show_field:
        get_first_tag(data, set([show_field]))
    if show_leader:
        print data[:24]
    if show_pos:
        print pos
    if verbose:
        show_book(data)
        print
    marc_rec = MarcBinary(data)
    edition_marc_bin = parse.read_edition(marc_rec)
    print edition_marc_bin
    if build_rec:
        pprint(build_record(data))
        print
    try:
        rec = read_edition(data)
    except SoundRecording:
        sound_rec += 1
        continue
    except BadDictionary:
        bad_dict += 1
        continue
    if not rec:
        if show_non_books:
            show_book(data)
            print
        not_book += 1
    else:
        book += 1
f.close()

print "total records:", total
print "sound recordings:", sound_rec
print "records with bad dictionary:", bad_dict
print "not books:", not_book
print "books:", book
