from openlibrary.api import OpenLibrary

ol = OpenLibrary('http://openlibrary.org/')

data = eval(open('update').read())

done = []

for author in data:
    print (author['key'], author['name'])
    akey = author['key']
    a = ol.get(akey)
    if not a.get('bio') and author['bio']:
        a['bio'] = author['bio']
        ol.save(akey, a, 'Add author bio from Smashwords.')

    for edition in author['editions']:
#        wkey = ol.new({
#            'type': '/type/work',
#            'title': edition['title'],
#            'authors': [{'author': {'key': akey}}],
#            'description': edition['description'],
#            'subjects': ['Lending library'],
#        })
#
        wkey = edition['work']
        w = ol.get(wkey)
        assert edition['description']
        if not w.get('description'):
            w['description'] = edition['description']
        if 'Lending library' not in w.get('subjects', []):
            w.setdefault('subjects', []).append('Lending library')
            ol.save(wkey, w, 'Add lending edition from Smashwords')
        continue

        q = {'type': '/type/edition', 'ocaid': edition['ia']}
        existing = list(ol.query(q))
        if existing:
            print existing
            print 'skip existing:', str(existing[0]), edition['ia']
            continue

        e = {
            'type': '/type/edition',
            'title': edition['title'],
            'authors': [{'key': akey}],
            'works': [{'key': wkey}],
            'ocaid': edition['ia'],
            'publishers': ['Smashwords'],
            'publish_date': edition['publish_date'],
        }
        if 'isbn' in edition:
            e['isbn'] = edition['isbn']
        ekey = ol.new(e, 'Add lending edition from Smashwords')
        print ekey, e['ocaid'], e['title']
        done.append(e['ocaid'])

print done
