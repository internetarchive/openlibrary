from catalog.db_read import withKey, get_things
import web, sys
from catalog.olwrite import Infogami

def key_int(rec):
    return int(web.numify(rec['key']))

def copy_fields(from_author, to_author, name):
    new_fields = { 'name': name, 'personal_name': name }
    for k, v in from_author.iteritems():
        print k
        if k in ('name', 'key', 'last_modified', 'type', 'id', 'revision'):
            continue
        if k in author:
            assert v == to_author[k]
        else:
            new_fields[k] = v
    return new_fields

def update_author(key, new):
    q = { 'key': key, }
    for k, v in new.iteritems():
        q[k] = { 'connect': 'update', 'value': v }
    print q
    print infogami.write(q, comment='merge author')
    print

def switch_author(old, new):
    q = { 'authors': old['key'], 'type': '/type/edition', }
    for key in get_things(q):
        edition = withKey(key)
        authors = []
        for author in edition['authors']:
            if author['key'] == old['key']:
                author_key = new['key']
            else:
                author_key = author['key']
            authors.append({ 'key': author_key })

        q = {
            'key': key,
            'authors': { 'connect': 'update_list', 'value': authors }
        }
        print infogami.write(q, comment='merge authors')

def make_redirect(old, new):
    q = {
        'key': old['key'],
        'location': {'connect': 'update', 'value': new['key'] },
        'type': {'connect': 'update', 'value': '/type/redirect' },
    }
    for k in old.iterkeys():
        if k not in ('key', 'last_modified', 'type', 'id', 'revision'):
            q[str(k)] = { 'connect': 'update', 'value': None }
    print q
    print infogami.write(q, comment='replace with redirect')

def merge_authors(author, merge_with, new_name):
    print 'merge author %s:"%s" and %s:"%s"' % (author['key'], author['name'], merge_with['key'], merge_with['name'])
    print 'becomes: "%s"' % new_name
    if key_int(author) < key_int(merge_with):
        new_key = author['key']
        print "copy fields from merge_with to", new_key
        new = copy_fields(merge_with, author, new_name)
        update_author(new_key, new)
        switch_author(merge_with, author)
#        print "delete merge_with"
        make_redirect(merge_with, author)
    else:
        new_key = merge_with['key']
        print "copy fields from author to", new_key
        new = copy_fields(merge_with, author, new_name)
        update_author(new_key, new)
        switch_author(author, merge_with)
#        print "delete author"
        make_redirect(author, merge_with)
    print


q = { 'name': 'Delia Smith', 'type': '/type/author' }
for key in get_things(q):
    print key

q = { 'title': 'OBE', 'type': '/type/author' }
for key in get_things(q):
    print key

author = withKey(sys.argv[1])
merge_with = withKey(sys.argv[2])

print author
#print merge_with

#merge_authors(author, merge_with, "Delia Smith")
