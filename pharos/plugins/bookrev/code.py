"""
Book reviews plugin.
"""
import sys
import web
import infogami
import forms
from infogami import tdb
from infogami import config
from infogami.core import auth, db
from infogami.utils import delegate, view

render = web.template.render('plugins/bookrev/templates/')
stdout = sys.stdout

def get_site():
    return db.get_site(config.site)

def get_type(type_name):
    site = get_site()
    return db.get_type(site, type_name)

def create_types():
    def create_type(type_name, prop_dict={}):
        def props():
            for pname, ptype_name in prop_dict.items():
                yield dict(name=pname, type=get_type(ptype_name), unique=False)
        site = get_site()
        return db._create_type(site, type_name, list(props()))

    create_type('type/reviewsource')
    create_type('type/bookreview', dict(
        book='type/edition',
        author='type/user',
        source='type/reviewsource',
        text='type/text',
        url='type/string'
    ))
    create_type('type/vote', dict(
        review='type/bookreview',
        user='type/user',
        weight='type/int'
    ))
    create_type('type/comment', dict(
        running_id='type/int',
        #target='type/anytype',
        author='type/user',
        #parent_comment='type/comment',
        text='type/text'
    ))

def insert_backreferences():
    def insert_backreference(type_name, name, rtype_name, rprop_name):
        type = get_type(type_name)
        d = dict(type=get_type(rtype_name), property_name=rprop_name)
        br = db._get_thing(type, name, get_type('type/backreference'), d)
        brs = type.get('backreferenes', [])
        brs.append(br)
        type.backreferences = brs
        type.save()

    insert_backreference('type/user', 'reviews', 'type/bookreview', 'author') 
    insert_backreference('type/edition', 'reviews', 'type/bookreview', 'book') 
    insert_backreference('type/bookreview', 'votes', 'type/vote', 'review') 
    insert_backreference('type/bookreview', 'comments', 'type/comment', 'target') 

def get_thing(name, type):
    site = get_site()
    try:
        thing = tdb.withName(name, site)
        if thing.type.id == type.id:
            return thing
    except tdb.NotFound:
        pass
    return None

def insert_book_review(edition, user, review_source, text):
    def unique_name():
        import uuid
        return 'r/%s/%s' % (web.lstrips(edition.name, 'b/'), uuid.uuid1())
    site = get_site()
    d = dict(book=edition, author=user, source=review_source)
    review = tdb.new(unique_name(), site, get_type('type/bookreview'), d)
    review.text = text
    review.save()
    return review

def get_review_source(name, create=True):
    type = get_type('type/reviewsource')
    rs = get_thing(name, type) 
    if not rs and create:
        site = get_site()
        rs = tdb.new(name, site, type, d=None)
        rs.save()
    return rs

@infogami.action
def install_bookrev():
    create_types()
    insert_backreferences()

@infogami.action
def write_a_review():
    
    EDITION = get_type('type/edition')
    USER = get_type('type/user')

    def new_user(username, email=''):
        site = get_site()
        username = web.lstrips(username, 'user/')
        user = db.new_user(site, username, email)
        user.displayname = username
        user.save()
        return user

    def lpad(s, lpad):
        if not s:
            return lpad
        elif s.startswith(lpad):
            return s
        else:
            return '%s%s' % (lpad, s)

    def read_text():
        lines = []
        line = raw_input()
        while line:
            lines.append(line)
            line = raw_input()
        return "\n\n".join(lines)

    class quit(Exception):
        pass

    class Shell:
        def __init__(self):
            self.edition = None
            self.user = None
            self.text = None
            self.rs = get_review_source('rs/plugging_reviews', create=True) # !!! tmp
        def get_edition(self):
            edefault = 'b/Heartbreaking_of_Genius_1'
            ename = raw_input('\nbook edition? [%s] ' % edefault)
            ename = ename or edefault 
            self.edition = get_thing(ename, EDITION)
            if not self.edition:
                print '\nbook edition not found.'
            else:
                print '\nbook edition %s found.' % self.edition
        def get_user(self):
            if not self.edition:
                raise quit()
            udefault = 'user/john'
            uname = raw_input('\nreview author? [%s] ' % udefault)
            uname = uname and lpad(uname, 'user/') or udefault
            self.user = get_thing(uname, USER)
            if not self.user:
                create = raw_input('\nreview author not found. create new? [n] ')
                if ('y' in create) or ('Y' in create):
                    self.user = new_user(uname)
                    print '\nok.'
                else:
                    return
            else:
                print '\nuser %s found.' % self.user
        def get_text(self): 
            if not self.edition or not self.user:
                raise quit()
            print '\ntype in the review. (exit by typing two continuous line breaks.)\n'
            self.text = read_text()        
            print '\nthanks.'

    _ = Shell()
    _.get_edition()
    _.get_user()
    _.get_text()

    review = insert_book_review(_.edition, _.user, _.rs, _.text)
    print '\ncreated review %s.' % review

def require_user(f):
    def g(*a, **kw):    
        self, site, params = a[0], a[1], a[2:]
        user = auth.get_user(site)
        if user:
            a = [self, site, user] + list(params)
            return f(*a, **kw)
        else:            
            return web.redirect('/login')
    return g

error = web.notfound

class addreview(delegate.page):

    @require_user
    def GET(self, site, user):
        i = web.input('edition')
        edition = get_thing(i.edition, get_type('type/edition'))
        if not edition:
            return error()
        form = forms.review_form()
        form.fill(edition=edition.name)
        return render.addreview(user, edition, form)

    @require_user
    def POST(self, site, user):
        form = forms.review_form()
        if form.validates():
            edition = get_thing(form.d.edition, get_type('type/edition'))
            if not edition:
                return error()
            review_source = get_review_source('rs/web_reviews', create=True)
            review = insert_book_review(edition, user, review_source, form.d.text)
            return web.redirect('/' + review.name)
        else:
            return render.addreview(user, edition, form)
        
class reviews(delegate.page):

    def GET(self, site):
        reviews = list(tdb.Things(type=get_type('type/bookreview'), limit=20))
        return render.reviews(reviews)

