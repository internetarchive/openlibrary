import web
from infogami import config, tdb
from infogami.core import db, thingutil

def get_site():
    return db.get_site(config.site)

def get_type(type_name):
    site = get_site()
    return db.get_type(site, type_name)

def create_type(type_name, properties={}):
    def props():
        for pname, ptype_name in properties.items():
            yield dict(name=pname, type=get_type(ptype_name), unique=True)

    return db._create_type(get_site(), type_name, list(props()))


def insert_backreference(type_name, prop_name, ref_type_name, ref_prop_name):

    type = get_type(type_name)

    def create_backreference(): 
        d = {'type': get_type(ref_type_name), 'property_name': ref_prop_name}
        return db._get_thing(type, 
                             prop_name, 
                             get_type('type/backreference'), 
                             d)

    type.backreferences = type.get('backreferences', [])
    type.backreferences.append(create_backreference())
    type.save()


fill_backreferences = thingutil.thingtidy

def get_thing(name, type):
    site = get_site()
    try:
        thing = tdb.withName(name, site)
        if thing.type.id == type.id:
            fill_backreferences(thing)
            return thing
    except tdb.NotFound:
        pass
    return None

def insert_book_review(edition, user, review_source, text, title=None):
    def unique_name():
        review_count = len(list(edition.get('reviews', [])))
        id = web.to36(review_count + 1)
        return '%s/review/%s' % (edition.name, id)
    site = get_site()
    d = dict(book=edition, author=user, source=review_source)
    review = tdb.new(unique_name(), site, get_type('type/bookreview'), d)
    review.text = text
    review.title = title or edition.title
    review.save(author=user)
    return review

def get_review_source(name, description='', create=True):
    type = get_type('type/reviewsource')
    rs = get_thing(name, type) 
    if not rs and create:
        site = get_site()
        rs = tdb.new(name, site, type, d=None)
        rs.description = description
        rs.save()
    return rs
