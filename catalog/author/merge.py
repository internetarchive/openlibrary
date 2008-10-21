from catalog.db_read import withKey, get_things
import web
from catalog.olwrite import Infogami

infogami = Infogami('pharosdb.us.archive.org:7070')
infogami.login('ImportBot', 'eephae6D')

def key_int(rec):
    return int(web.numify(rec['key']))

def copy_fields(from_author, to_author, name):
    new_fields = { 'name': name, 'personal_name': name }
    for k, v in from_author.iteritems():
        if k in ('name', 'key'):
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
    print infogami.write(q, comment='merge author')

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
        infogami.write(q, comment='merge authors')

def make_redirect(old, new):
    q = {
        'key': old['key'],
        'location': {'connect': 'update', 'value': new['key'] },
        'type': {'connect': 'update', 'value': '/type/redirect' },
    }
    for k in old.iterkeys():
        if k != 'key':
            q[str(k)] = { 'connect': 'update', 'value': None }
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


