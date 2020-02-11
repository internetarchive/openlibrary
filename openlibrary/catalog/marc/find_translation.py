#!/usr/bin/python2.5
from __future__ import print_function
from catalog.marc.fast_parse import *
import sys
import codecs

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

for data, length in read_file(open(sys.argv[1])):
    line = get_first_tag(data, set(['500']))
    if not line:
        continue
    subtag, value = next(get_all_subfields(line))
    if subtag != 'a':
        continue
    if value.startswith("Translation of the author's thesis"):
        continue
    start = value.lower().find('translation of')
    if start == -1 or start > 6:
        continue
    print(value)
