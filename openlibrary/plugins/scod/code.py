from infogami.utils import delegate
from infogami.utils.view import render, require_login, public, permission_denied, safeint
from infogami import config
import web
import datetime

@public
def get_scan_status(key):
    record = get_scan_record(key)
    return record and record.scan_status

def get_email(user):
    try:
        delegate.admin_login()
        return web.utf8(web.ctx.site.get_user_email(user.key).email)
    finally:
        web.ctx.headers = []

def get_scan_record(key):
    key = "/scan_record" + key
    record = web.ctx.site.get(key)
    if record and record.type and record.type.key == '/type/scan_record':
        return record
    else:
        return None

def error(message):
    raise web.HTTPError("200 OK", {}, "ERROR: " + message)

def get_book(path, check_scanned=True, check_ocaid=True):
    page = web.ctx.site.get(path)
    if not page:
        error('Invalid book: ' + page)
    elif page.type.key != '/type/edition':
        error(path + ' is not a book')
    elif check_ocaid and page.ocaid:
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

        def get_to():
            if config.get('plugin_scod') is not None:
                return config.plugin_scod.get('email_recipients', [])
            else:
                return config.get('scan_email_recipients', [])
        
        to = get_to()
        if to:
            scan_record = get_scan_record(path)
            message = render.scan_request_email(book, scan_record)
            web.sendmail(config.from_address, to, message.subject.strip(), message)

        to = get_email(user)
        message = render.scan_waiting_email(book, scan_record)
        web.sendmail(config.from_address, to, message.subject.strip(), message)
        return render.scan_inprogress(book)
        
class scan_book_notfound(delegate.mode):
    def is_scan_user(self):
        usergroup = web.ctx.site.get('/usergroup/scan')
        user = web.ctx.site.get_user()
        return user and usergroup and user.key in (m.key for m in usergroup.members)

    def POST(self, path):
        if not self.is_scan_user():
            return permission_denied('Permission denied.')

        book = web.ctx.site.get(path)
        i = web.input("scan_status", _comment=None)
        
        q = {
            'key': '/scan_record' + path,
            'scan_status': {
                'connect': 'update',
                'value': i.scan_status
            }
        }
        web.ctx.site.write(q, i._comment)

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
            if i.scan_status == 'SCAN_IN_PROGRESS':
                message = render.scan_inprogress_email(book, scan_record, i._comment)
            else:    
                message = render.scan_book_notfound_email(book, scan_record, i._comment)
            web.sendmail(config.from_address, to, message.subject.strip(), str(message), cc=cc)
        raise web.seeother(web.changequery(query={}))
        
class scan_inprogress(scan_book_notfound):
    pass

class scan_complete(delegate.mode):
    def is_scan_user(self):
        usergroup = web.ctx.site.get('/usergroup/scan')
        user = web.ctx.site.get_user()
        return user and usergroup and user.key in (m.key for m in usergroup.members)

    def GET(self, path):
        if not self.is_scan_user():
            return permission_denied('Permission denied.')

        book = get_book(path, check_scanned=False, check_ocaid=False)
        return render.scan_complete(book)
        
    def POST(self, path):
        if not self.is_scan_user():
            return permission_denied('Permission denied.')

        book = get_book(path, check_scanned=False, check_ocaid=False)
        i = web.input("ocaid", volumes=None, multivolume_work=None, _comment=None)
        
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

        if i.multivolume_work:
            def volume(index, ia_id):
                return {
                    'type': {'key': '/type/volume'},
                    'volume_number': index,
                    'ia_id': ia_id
                }
                    
            volumes = i.volumes and i.volumes.split() or []
            q[0]['volumes'] = {
                'connect': 'update_list',
                'value': [volume(index+1, v) for index, v in enumerate(volumes)]
            }
            q[0]['ocaid'] = {
                'connect': 'update',
                'value': ''
            }

        web.ctx.site.write(q, i._comment)

        scan_record = get_scan_record(path)
        to = scan_record.sponsor and get_email(scan_record.sponsor)
        cc = getattr(config, 'scan_email_recipients', [])
        if to:
            message = render.scan_complete_email(book, scan_record, i._comment)
            web.sendmail(config.from_address, to, message.subject.strip(), str(message), cc=cc)

        raise web.seeother(web.changequery(query={}))

def get_scan_queue(scan_status, limit=None, offset=None):
    q = {
        'type': '/type/scan_record',
        'scan_status': scan_status,
        'sort': '-last_modified'
    } 
    if limit:
        q['limit'] = limit
    
    if offset:
        q['offset'] = offset
        
    keys = web.ctx.site.things(q)
    result = web.ctx.site.get_many(keys)

    # prefetch editions
    web.ctx.site.get_many([web.lstrips(key, '/scan_record') for key in keys])

    # prefetch scanning centers
    scanning_centers = set(r.locations[0].key for r in result if r.locations)
    web.ctx.site.get_many(list(scanning_centers))

    return result

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
        i = web.input(status="WAITING_FOR_BOOK", p=None)
        options = ["NOT_SCANNED", "WAITING_FOR_BOOK", "BOOK_NOT_SCANNED", "SCAN_IN_PROGRESS", "SCAN_COMPLETE"]
        if i.status not in options:
            raise web.seeother(web.changequery({}))
            
        offset = safeint(i.p, 0) * 50
            
        records = get_scan_queue(i.status, limit=50, offset=offset)
        return render.scan_queue(records)
