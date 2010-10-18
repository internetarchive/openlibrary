from openlibrary.catalog.utils.query import query, withKey
from openlibrary.catalog.importer.update import add_source_records

for num, line in enumerate(open('/1/edward/imagepdf/possible_match2')):
    doc = eval(line)
    if 'publisher' not in doc:
        continue
    item_id = doc['item_id']
    if query({'type':'/type/edition','source_records':'ia:' + item_id}):
        continue
    e = withKey(doc['ol'])
    if 'publishers' not in e:
        continue
    title_match = False
    if doc['title'] == e['title']:
        title_match = True
    elif doc['title'] == e.get('title_prefix', '') + e['title']:
        title_match = True
    elif doc['title'] == e.get('title_prefix', '') + e['title'] + e.get('subtitle', ''):
        title_match = True
    elif doc['title'] == e['title'] + e.get('subtitle', ''):
        title_match = True
    if not title_match:
        continue
    if doc['publisher'] != e['publishers'][0]:
        continue
    print 'match:', item_id, doc['ol']
    add_source_records(doc['ol'], item_id)

