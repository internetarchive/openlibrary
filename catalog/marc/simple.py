#!/usr/bin/python2.5
from catalog.marc.fast_parse import *
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
build_rec = False
show_field = None

opts, files = getopt(sys.argv[1:], 'v', ['verbose', 'show-non-books', 'build-record', 'show-field='])

for o, a in opts:
    if o == '--show-non-books':
        show_non_books = Tru
    elif o in ('-v', '--verbose'):
        verbose = True
    elif o == '--build-record':
        from build_record import build_record
        from pprint import pprint
        build_rec = True
    elif o == '--show-field':
        show_field = a

# simple parse of a MARC binary, just counts types of items

def show_book(data):
    print 'leader:', data[:24]
    for tag, line in get_all_tag_lines(data):
        if tag.startswith('00'):
            print tag, line[:-1]
        else:
            print tag, line[0:2], fmt_subfields(line)

total, sound_rec, not_book, book = 0, 0, 0, 0
for data, length in read_file(open(files[0])):
    total += 1
    if show_field:
        get_first_tag(data, set([show_field]))
    if verbose:
        show_book(data)
        print
    if build_rec:
        pprint(build_record(data))
        print
    try:
        rec = read_edition(data)
    except SoundRecording:
        sound_rec += 1
        continue
    if not rec:
        if show_non_books:
            show_book(data)
            print
        not_book += 1
    else:
        book += 1

print "total records:", total
print "sound recordings:", sound_rec
print "not books:", not_book
print "books:", book
