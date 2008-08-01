from infogami.utils import delegate
from infogami.utils.view import render, require_login, public
from infogami import config
import web

@public
def get_scan_status(key):
    key = "/scan_record" + key
    record = web.ctx.site.get(key)
    return record and record.scan_status

def get_scan_record(key):
    key = "/scan_record" + key
    return  web.ctx.site.get(key)

def error(message):
    print 'ERROR:', message
    raise StopIteration

def get_book(path, check_scanned=True):
    page = web.ctx.site.get(path)
    if not page:
        error('Invalid book: ' + page)
    elif page.type.key != '/type/edition':
        error(path + ' is not a book')
    elif page.ocaid:
        error('This book is already scanned')
    elif check_scanned and get_scan_status(path) != 'NOT_SCANNED':
        error(path + ' is not scannable.')
    else:    
        return page
        
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
        scanning_center = get_scan_record(path).locations[0].name
        return render.scod_review(book, scanning_center)
    
    @require_login
    def POST(self, path):
        book = get_book(path)
        record = get_scan_record(path)
        user = web.ctx.site.get_user()
        delegate.admin_login()
        q = {
            'key': '/scan_record' + path,
            'scan_status': {
                'connect': 'update',
                'value': 'WAITING_FOR_BOOK'
            },
            'sponsor': {
                'connect': 'update',
                'key': user.key
            },
        }
        try:
            web.ctx.site.write(q)
        finally:
            web.ctx.headers = []
        
        to = getattr(config, 'scod_email_recipients', [])
        if to:
            scan_record = get_scan_record(path)
            message = render.scod_request_email(book, scan_record)
            web.sendmail(config.from_address, to, message.subject.strip(), message)
    
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
        book = get_book(path, check_scanned=False)
        return render.scod_complete(book)
        
    def POST(self, path):
        self.assert_scod_user()
        book = get_book(path, check_scanned=False)
        i = web.input("ocaid")
        
        q = [
            {
                'key': path,
                'ocaid': {
                    'connect': 'update',
                    'value': i.ocaid
                }
            },
            {
                'key': '/scan_record' + path,
                'scan_status': {
                    'connect': 'update',
                    'value': 'SCAN_COMPLETE'
                }
            }
        ]
        web.ctx.site.write(q)

        def get_email(user):
            try:
                delegate.admin_login()
                return web.utf8(web.ctx.site.get_user_email(user.key).email)
            finally:
                web.ctx.headers = []

        scan_record = get_scan_record(path)
        to = scan_record.sponsor and get_email(scan_record.sponsor)
        cc = getattr(config, 'scod_email_recipients', [])
        if to:
            message = render.scod_complete_email(book, scan_record)
            web.sendmail(config.from_address, to, message.subject.strip(), str(message), cc=cc)

        web.seeother(web.changequery(query={}))

def get_scod_queue():
    def f(scan_status):
        q = {
            'type': '/type/scan_record',
            'scan_status': scan_status,
        } 
        result = web.ctx.site.things(q)
        return [web.ctx.site.get(key) for key in result]

    result = f('WAITING_FOR_BOOK') + f('SCAN_IN_PROGRESS')
    result.sort(key=lambda record: record.last_modified, reverse=True)
    return result

class scan_queue(delegate.page):
    def GET(self):
        queue = get_scod_queue()
        return render.scod_queue(queue)
