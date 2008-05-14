from time import time
from pprint import pprint
from catalog.marc.MARC21 import MARC21Record
from catalog.marc.parse import pick_first_date
import urllib2

entity_fields = ('name', 'birth_date', 'death_date', 'date')

def find_entity(site, entity):
    entity = dict((k, entity[k]) for k in entity_fields if k in entity)
    print entity
    things = site.things(entity)
    if not things:
        print "person not found"
        return

    print "found", len(things), "match"
    for key in things:
        db_entity = site.withKey(key, lazy=False)._get_data()
        pprint(db_entity)
        for field in entity_fields:
            if field in entity:
                assert field in db_entity
            else:
                assert field not in db_entity

def get_from_archive(locator):
    (file, offset, length) = locator.split (":")
    offset = int (offset)
    length = int (length)

    r0, r1 = offset, offset+length-1
    url = 'http://www.archive.org/download/%s'% file

    assert 0 < length < 100000

    ureq = urllib2.Request(url, None, {'Range':'bytes=%d-%d'% (r0, r1)},)
    result = urllib2.urlopen(ureq).read(100000)
    rec = MARC21Record(result)
    return rec

def contrib(r):
    contribs = []
    for f in r.get_fields('700'):
        print f.subfield_sequence
        contrib = {}
        if 'a' not in f.contents and 'c' not in f.contents:
            continue # should at least be a name or title
        name = " ".join([j.strip(' /,;:') for i, j in f.subfield_sequence if i in 'abc'])
        if 'd' in f.contents:
            contrib = pick_first_date(f.contents['d'])
            contrib['db_name'] = ' '.join([name] + f.contents['d'])
        else:
            contrib['db_name'] = name
        contrib['name'] = name
        contrib['entity_type'] = 'person'
        subfields = [
            ('a', 'personal_name'),
            ('b', 'numeration'),
            ('c', 'title')
        ]
        for subfield, field_name in subfields:
            if subfield in f.contents:
                contrib[field_name] = ' '.join([x.strip(' /,;:') for x in f.contents[subfield]])
        if 'q' in f.contents:
            contrib['fuller_name'] = ' '.join(f.contents['q'])
        contribs.append(contrib)

    for f in r.get_fields('710'):
        print f.subfield_sequence
        contrib = {
            'entity_type': 'org',
            'name': " ".join([j.strip(' /,;:') for i, j in f.subfield_sequence if i in 'ab'])
        }
        contrib['db_name'] = contrib['name']
        contribs.append(contrib)

    for f in r.get_fields('711'):
        print f.subfield_sequence
        contrib = {
            'entity_type': 'event',
            'name': " ".join([j.strip(' /,;:') for i, j in f.subfield_sequence if i in 'acdn'])
        }
        contrib['db_name'] = contrib['name']
        contribs.append(contrib)
    return contribs

def load(site, filename):
    for line in open(filename):
        isbn, lc_src, amazon = eval(line)
        versions = site.versions({'machine_comment': lc_src})
        assert len(versions) == 1
        thing = site.withID(versions[0]['thing_id'])
        
        if 'authors' not in amazon:
            continue
        author_count = 0
        for name, role in amazon['authors']:
            if role != 'Author':
                continue
            author_count+=1
            if author_count > 1:
                break
        if author_count < 2:
            continue

        print lc_src
        print 'amazon:', amazon['authors']


        try:
            print 'LC authors:', [x.name for x in thing.authors]
        except AttributeError:
            print 'no authors in LC'
        lc_contrib = []
        try:
            lc_contrib = thing.contributions
            print 'LC contributions:', lc_contrib
        except AttributeError:
            print 'no contributions in LC'
        if lc_contrib:
            r = get_from_archive(lc_src)
            contrib_detail = contrib(r)
            assert len(lc_contrib) == len(contrib_detail)
            for c, detail in zip(lc_contrib, contrib_detail):
                print c,
                find_entity(site, detail)
        print
        continue
        print "LC"
        pprint (thing._get_data())
        print "Amazon"
        pprint (amazon)
        print
    #    for x in web.query("select thing_id from version where machine_comment=" + web.sqlquote(lc)):
    #        t = site.withID(x.thing_id)
    #        print t.title


