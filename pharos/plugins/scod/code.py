from infogami.utils import delegate
from infogami.utils.view import render, require_login
import web

def error(message):
    print 'ERROR:', message
    raise StopIteration

def get_book(path):
    page = web.ctx.site.get(path)
    if not page:
        error('Invalid book: ' + page)
    elif page.type.key != '/type/edition':
        error(path + ' is not a book')
    elif page.ocaid:
        error('This book is already scanned')
    elif not page.location or page.location[0] not in SCANNING_CENTERS:
        error(path + ' is not scannable.')
    else:    
        return page
        
SCANNING_CENTERS = {
    "BPL1": "BPL Central Library - Copley Square (circulating)",
    "BPL1FA": "BPL Central - Fine Arts",
    "BPL1GD": "BPL Central - Government Documents",
    "BPL1GR": "BPL Central - General Reference",
    "BPL1HU": "BPL Central - Humanities",
    "BPL1ILL": "BPL Central - ILL",
    "BPL1MC": "BPL Central - Leventhal Map Center",
    "BPL1MI": "BPL Central - Microtext",
    "BPL1MU": "BPL Central - Music",
    "BPL1NE": "BPL Central - Newspapers",
    "BPL1PR": "BPL Central - Print",
    "BPL1RB": "BPL Central - Rare Books",
    "BPL1RSO": "BPL Central - Regional Services",
    "BPL1SA": "BPL Central - Sound Archives",
    "BPL1SC": "BPL Central - Science",
    "BPL1SO": "BPL Central - Social Sciences",
    "BPL1SP": "BPL Central - Special Collections",
    "BPL1ST": "BPL Central - Book Delivery",
    "BPL1TR": "BPL Central - Telephone Reference",
}

class scod_confirm(delegate.mode):
    def GET(self, path):
        book = get_book(path)
        print render.scod_confirm(book)

class scod_login(delegate.mode):
    def GET(self, path):
        book = get_book(path)
        print render.scod_login(book)
        
class scod_review(delegate.mode):
    @require_login
    def GET(self, path):
        book = get_book(path)
        scanning_center = SCANNING_CENTERS[book.location[0]]
        return render.scod_review(book, scanning_center)
    
    @require_login
    def POST(self, path):
        book = get_book(path)
        return render.scod_inprogress(book)

class scod_complete(delegate.mode):
    def assert_scod_user(self):
        usergroup = web.ctx.site.get('/usergroup/scod')
        user = web.ctx.site.get_user()
        
        if user and usergroup and user.key in (m.key for m in usergroup.members):
            return True
        else:
            print "Permission denied"
            raise StopIteration
        
    def GET(self, path):
        self.assert_scod_user()
        book = get_book(path)
        return render.scod_complete(book)
        
    def POST(self, path):
        self.assert_scod_user()
        book = get_book(path)
        i = web.input("ocaid")
        
        q = {
            'key': path,
            'ocaid': {
                'connect': 'update',
                'value': i.ocaid
            }
        }
        web.ctx.site.write(q)
        web.seeother(web.changequery(query={}))
