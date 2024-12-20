"""Library for managing Open Library data"""

import json

from openlibrary.data.dump import pgdecode


def parse_data_table(filename):
    """Parses the dump of data table and returns an iterator with
    <key, type, revision, json> for all entries.
    """
    for line in open(filename):
        thing_id, revision, json_data = pgdecode(line).strip().split("\t")
        d = json.loads(json_data)
        yield d['key'], d['type']['key'], str(d['revision']), json_data
