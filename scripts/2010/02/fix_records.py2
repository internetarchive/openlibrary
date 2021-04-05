# - remove title_prefix
# - fix bad unicode
# - source_records field
# - change table_of_contents from to a list of /type/toc_item
# - undelete any deleted authors
# - delete blank toc

# [{'type': {'key': '/type/toc_item'}, 'class': 'section'}]

import sys, codecs
import simplejson as json

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

for line in open('/2/edward/fix_bad/edition_file'):
    cur = json.loads(line)
    has_blank_toc = False
    print cur
    if 'table_of_contents' in cur and len(cur['table_of_contents']) == 1:
        toc = cur['table_of_contents'][0]
        if isinstance(toc, dict) and toc['type']['key'] == '/type/toc_item' \
            and 'label' not in toc and 'title' not in toc:
                has_blank_toc = True
    for k, v in cur.items():
        print "%20s: %s" % (k, v)
    print 'blank toc:', has_blank_toc
    print
