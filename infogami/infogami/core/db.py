from infogami.utils import delegate
import web
from infogami import tdb
import infogami
from infogami.tdb import NotFound
import pickle

#@@ move to some better place
@infogami.install_hook
@infogami.action
def tdbsetup():
    """setup tdb for infogami."""
    from infogami import config
    web.load()
    # hack to disable tdb hooks
    tdb.tdb.hooks = []
    tdb.setup()
    sitetype = get_type('site') or new_type('site')
    sitetype.save()
    pagetype = get_type('page') or new_type('page')
    pagetype.save()

    try:
        tdb.withName(config.site, sitetype)
    except:
        tdb.new(config.site, sitetype, sitetype).save()
    
class ValidationException(Exception): pass

def get_version(site, path, revision=None):
    return tdb.withName(path, site, revision=revision and int(revision))

def new_version(site, path, type, data):
    try:
        p = tdb.withName(path, site)
        p.type = type
        p.setdata(data)
    except tdb.NotFound:
        p = tdb.new(path, site, type, data)
    
    return p
    
def get_user(userid):
    try:
        return tdb.withID(userid)
    except NotFound:
        return None

def get_user_by_name(username):
    try:
        return tdb.withName(username, tdb.usertype)
    except NotFound:
        return None
    
def login(username, password):
    try:
        u = get_user_by_name(username)
        if u and (u.password == password):
            return u
        else:
            return None
    except tdb.NotFound:
        return None
    
def new_user(username, email, password):
    d = dict(email=email, password=password)
    return tdb.new(username, tdb.usertype, tdb.usertype, d)

def get_user_preferences(user):
    type = get_type('preferences', create=True)
    try:
        return tdb.withName('preferences', user)
    except NotFound:
        return tdb.new('preferences', user, type)
    
def get_recent_changes(site):
    raise Exception, "Not implemented"
    
def pagelist(site):
    raise Exception, "Not implemented"

def get_type(name, create=False):
    try:
        return tdb.withName(name, tdb.metatype)
    except tdb.NotFound:
        if create:
            type = new_type(name)
            type.save()
            return type
        else:
            return None

def new_type(name):
    return tdb.new(name, tdb.metatype, tdb.metatype)

def get_site(name):
    return tdb.withName(name, get_type("site"))

def list_pages(site, path):
    """Lists all pages with name path/*"""
    
    if path == "":
        pattern = '%'
    else:
        pattern = path + '/%'
    return web.query("""SELECT t.id, t.name FROM thing t 
            JOIN version ON version.revision = t.latest_revision AND version.thing_id = t.id
            JOIN datum ON datum.version_id = version.id 
            JOIN thing type ON type.id = datum.value  AND datum.key = '__type__'
            WHERE t.parent_id=$site.id AND t.name LIKE $pattern AND type.name != 'delete' 
            ORDER BY t.name""", vars=locals())
       
from infogami.utils.view import public
        
#@@ this should be moved to wikitemplates plugin    
@public
def get_schema(site, type):
    try:
        p = get_version(site, 'templates/%s/schema' % type.name)
        return p.d
    except tdb.NotFound:
        return web.storage({'*': 'string'})
        
def get_site_permissions(site):
    if hasattr(site, 'permissions'):
        return pickle.loads(site.permissions)
    else:
        return {}
    
def set_site_permissions(site, permissions):
    site.permissions = pickle.dumps(permissions)
    site.save()
