# this is copied from the bookrev module, need to put it
# into a common location @@

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
