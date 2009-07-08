from infogami.utils.delegate import mode, page
from infogami.utils.view import render
from infogami.core import db
from infogami.infobase import client
import simplejson
import urllib, web, httplib

class APIConnection:
    def __init__(self, server):
        self.server =  server

    def request(self, sitename, path, method="GET", data=None):
        path = "/api" + path
        data = data and urllib.urlencode([(k, v) for k, v in data.items() if k and v])
        if method == "GET" and data:
            path = path + "?" + data
            data = None

        conn = httplib.HTTPConnection(self.server)
        env = web.ctx.get('env') or {}
        
        cookie = env.get('HTTP_COOKIE')
        if cookie:
            headers = {'Cookie': cookie}
        else:
            headers = {}
        
        conn.request(method, path, data, headers=headers)
        response = conn.getresponse()
        data = response.read()

        return data and simplejson.loads(data)

def get_site():
    return client.Site(APIConnection('openlibrary.org'), 'openlibrary.org')

class sync_diff(mode):
    def GET(self, path):
        p = db.get_version(path) or web.ctx.site.new(path, {'key': path, 'revision': 0})
        p.revision = "%s - staging" % p.revision
        p2 = get_site().get(path) or web.ctx.site.new(path, {'key': path, 'revision': 0})
        p2.revision = "%s - production" % p2.revision
        return render.syncdiff(p, p2)

class sync(page):
    def GET(self): 
        paths = ["/templates/*", "/macros/*", "/about/*", "/dev/*", "/i18n*", "/index.*"]
        keys = ["/", "/i18n", "/tour"]
        
        for p in paths:
            keys += web.ctx.site.things({"key~": p})

        def modified(key):
            a = site1.get(key)._getdata()
            a.pop('revision', None)
            a.pop('last_modified', None)
            a.pop('latest_revision', None)

            b = site2.get(key)
            b = b and b._getdata()
            if not b: return True
            b.pop('revision', None)
            b.pop('last_modified', None)
            b.pop('latest_revision', None)
            #print >> web.debug, key, a, b
            return a != b

        site1 = web.ctx.site
        site2 = get_site()

        keys = [k for k in sorted(keys) if modified(k)]
        return render.sync(keys)
            
class sync_pull(mode):
    def GET(self, path):
        return """
            <h2>Pull %s from production to staging</h2>
            <form method="POST">
                <input type="submit" value="Pull"/>
            </form>
            """ % path

    def POST(self, path):
        site1 = get_site()
        page = site1.get(path)

        if page is None:
            print "page not found"

        save_page(web.ctx.site, page, "pulled from production")
        web.seeother("/sync")

def save_page(site, page, comment):
    def make_query(v):
        if isinstance(v, list):
            v = dict(connect='upadte_list', value=v)
        elif isinstance(v, dict):
            v['connect'] = 'update'
        else:
            v = dict(connect='update', value=v)
        return v

    d = page.dict()
    d.pop('latest_revision', None)
    for k, v in d.items():
        if k not in ['key']:
            d[k] = make_query(v)
    
    d['create'] = 'unless_exists'
    site.write(d, comment)

class sync_push(mode):
    def GET(self, path):
        return """
            <h2>Push %s from staging to production</h2>
            <form method="POST">
                <input type="submit" value="Push"/>
            </form>
            """ % path

    def POST(self, path):
        page = web.ctx.site.get(path)
        web.connect('postgres', db='infobase_production', host='pharosdb', user='anand', pw='')
        save_page(get_site(), page, "pushed from staging")
        web.seeother("/sync")
