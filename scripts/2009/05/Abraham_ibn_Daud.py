#!/usr/bin/python
from catalog.marc.fast_parse import get_subfields
from catalog.wikipedia.lookup import name_lookup, look_for_match, pick_from_match, more_than_one_match
from catalog.utils import pick_first_date
from pprint import pprint

marc = [
    '  \x1faAbraham ben David,\x1fcha-Levi,\x1fdca. 1110-ca. 1180\x1e',
    '  \x1faAbraham ben David,\x1fcha-Lev\xe2i,\x1fdca.1110-ca.1180\x1e',
    '  \x1faIbn Daud, Abraham ben David,\x1fcha-Levi,\x1fdca. 1100-1180\x1e',
    '  \x1faIbn Daud, Abraham ben David,\x1fcHalevi,\x1fdca. 1110-ca. 1180\x1e',
]

# wiki names: abraham ibn daud; abraham ibn david; ibn daub; ibn daud; avraham ibn daud

def test_lookup():
    for line in marc:
        fields = tuple((k, v.strip(' /,;:')) for k, v in get_subfields(line, 'abcd'))
        found = name_lookup(fields)
        for i in found:
            print i
        dates = pick_first_date(v for k, v in fields if k == 'd')
        print dates
        match = look_for_match(found, dates, False)
        print len(match)
        for i in match:
            print i
        #pprint(match)
        if len(match) != 1:
            match = pick_from_match(match)
        if len(match) != 1:
            for i in more_than_one_match(match):
                print i
        print

test_lookup()
