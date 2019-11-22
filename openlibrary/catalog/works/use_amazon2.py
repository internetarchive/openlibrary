from __future__ import print_function

import codecs
import dbhash
import os
import re
import sys

from catalog.amazon.other_editions import find_others
from catalog.get_ia import get_data
from catalog.infostore import get_site
from catalog.marc.build_record import build_record
from catalog.marc.fast_parse import get_all_subfields, get_tag_lines
from catalog.read_rc import read_rc

sys.stdout = codecs.getwriter("utf-8")(sys.stdout)
rc = read_rc()
db = dbhash.open(rc["index_path"] + "isbn_to_marc.dbm", "r")

site = get_site()

dir = sys.argv[1]
for filename in os.listdir(dir):
    if not filename[0].isdigit():
        continue
    l = find_others(filename, dir)
    if len(l) < 8:
        continue
    print(filename, len(l))
