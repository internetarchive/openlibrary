"""Library for managing Open Library data"""

import simplejson
import re

from dump import pgdecode

def parse_data_table(filename):
    """Parses the dump of data table and returns an iterator with 
    <key, type, revision, json> for all entries.
    """
    for line in open(filename):
        thing_id, revision, json = pgdecode(line).strip().split("\t")
        d = simplejson.loads(json)
        yield d['key'], d['type']['key'], str(d['revision']), json

