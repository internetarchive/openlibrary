import web, infogami
from infogami import tdb

import db, reviewsources, utils

def list_latest_reviews():
    for review in tdb.Things(type=db.get_type('type/bookreview'), limit=40):
        print '[%s] %s (%s)' % (review.author, review.book, review.source)

def simple_shell():
    """A simple shell for creating book reviews. For dev use only."""
    
    def create_dummy_user(username, password, displayname=None, email=''):

        username = web.lstrips(username, 'user/')
        displayname = displayname or username

        from infogami.core.db import new_user # hack
        user = new_user(db.get_site(), username, displayname, email, password)
        user.displayname = username
        user.save()

        return user


    class quit(Exception):
        pass


    class Shell:
        def __init__(self):
            self.edition = None
            self.user = None
            self.text = None
            self.rs = reviewsources.data.get('dev')

        def safety_lock(self, query):
            confirm = raw_input('\n%s [n] ' % query)
            if ('y' in confirm) or ('Y' in confirm):
                return
            else:
                raise quit()

        def input_edition_name(self, default=''):
            name = raw_input('\nbook edition? [%s] ' % default) or default
            self.edition = db.get_thing(name, db.get_type('type/edition'))
            if not self.edition:
                print '\nbook edition not found.'
            else:
                print '\nbook edition %s found.' % self.edition

        def input_user_name(self, default=''):
            if not self.edition:
                raise quit()
            name = raw_input('\nreview author? [%s] ' % default) or default
            self.user = db.get_thing(utils.lpad(name, 'user/'), 
                                     db.get_type('type/user'))
            if not self.user:
                print '\nreview author not found.'
                self.safety_lock('create a dummy user \'%s\'?' % name)
                self.user = create_dummy_user(name, password='test')
                print '\nok.'
            else:
                print '\nuser %s found.' % self.user

        def input_text(self): 
            if not self.edition or not self.user:
                raise quit()
            print '\ntype in the review. (exit by typing two continuous line breaks.)\n'
            self.text = utils.read_text()        
            print '\nthanks.'

    try:

        _ = Shell()
        _.safety_lock('\nthis shell is meant for dev use only. continue?')

        _.input_edition_name(default='b/Heartbreaking_of_Genius_1')
        _.input_user_name(default='test')
        _.input_text()

        review = db.insert_book_review(_.edition, _.user, _.rs, _.text)
        print '\ncreated review %s.' % review

    except quit:
        print 'exiting.'

