from infogami.utils import delegate
from infogami.utils.view import render, require_login, public
from infogami import config
import web
import datetime

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
        
class scan_confirm(delegate.mode):
    def GET(self, path):
        book = get_book(path)
        print render.scan_confirm(book)

class scan_login(delegate.mode):
    def GET(self, path):
        book = get_book(path)
        print render.scan_login(book)
        
class scan_review(delegate.mode):
    @require_login
    def GET(self, path):
        book = get_book(path)
        scanning_center = get_scan_record(path).locations[0].name
        return render.scan_review(book, scanning_center)
    
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
            'request_date': {
                'connect': 'update',
                'value': datetime.datetime.utcnow().isoformat()
            }
        }
        try:
            web.ctx.site.write(q)
        finally:
            web.ctx.headers = []
        
        to = getattr(config, 'scan_email_recipients', [])
        if to:
            scan_record = get_scan_record(path)
            message = render.scan_request_email(book, scan_record)
            web.sendmail(config.from_address, to, message.subject.strip(), message)
    
        return render.scan_inprogress(book)

class scan_complete(delegate.mode):
    def assert_scan_user(self):
        usergroup = web.ctx.site.get('/usergroup/scan')
        user = web.ctx.site.get_user()
        
        if user and usergroup and user.key in (m.key for m in usergroup.members):
            return True
        else:
            print "Permission denied"
            raise StopIteration
        
    def GET(self, path):
        self.assert_scan_user()
        book = get_book(path, check_scanned=False)
        return render.scan_complete(book)
        
    def POST(self, path):
        self.assert_scan_user()
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
                },
                'completion_date': {
                    'connect': 'update',
                    'value': datetime.datetime.utcnow().isoformat()
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
        cc = getattr(config, 'scan_email_recipients', [])
        if to:
            message = render.scan_complete_email(book, scan_record)
            web.sendmail(config.from_address, to, message.subject.strip(), str(message), cc=cc)

        web.seeother(web.changequery(query={}))

def get_scan_queue(scan_status, limit=None):
    q = {
        'type': '/type/scan_record',
        'scan_status': scan_status,
        'sort': 'last_modified'
    } 
    if limit:
        q['limit'] = limit
    result = web.ctx.site.things(q)
    return [web.ctx.site.get(key) for key in result]

@public
def to_datetime(iso_date_string):
    """
        >>> t = '2008-01-01T01:01:01.010101'
        >>> to_timestamp(t).isoformat()
        '2008-01-01T01:01:01.010101'
    """
    if not iso_date_string:
        return None

    try:
        #@@ python datetime module is ugly. 
        #@@ It takes so much of work to create datetime from isoformat.
        date, time = iso_date_string.split('T', 1)
        y, m, d = date.split('-')
        H, M, S = time.split(':')
        S, ms = S.split('.')
        return datetime.datetime(*map(int, [y, m, d, H, M, S, ms]))
    except:
        return None

class scan_queue(delegate.page):
    def GET(self):
        queue = web.storage(
            waiting=get_scan_queue('WAITING_FOR_BOOK'),
            inprogress=get_scan_queue('SCAN_IN_PROGRESS'),
            completed=get_scan_queue('SCAN_COMPLETE', limit=10))
        return render.scan_queue(queue)
