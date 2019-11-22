import sys

import simplejson as json
import web
from catalog.get_ia import get_from_local
from catalog.importer.db_read import get_mc, withKey
from catalog.marc.fast_parse import get_all_subfields, get_tag_lines


def get_src(key):
    e = withKey(key)
    if "source_records" in e:
        return e["source_records"]
    src = get_mc(key)
    if src:
        return [src]


def get_651(key):
    found = []
    for src in get_src(key):
        data = get_from_local(src)
        for tag, line in get_tag_lines(data, ["651"]):
            found.append(list(get_all_subfields(line)))
    return found


urls = ("^(/b/OL\d+M)$", "lookup")
app = web.application(urls, globals())


class lookup:
    def GET(self, key):
        return json.dumps(get_651(key))


if __name__ == "__main__":
    app.run()
