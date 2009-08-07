import py.test
import os.path
import web
import simplejson
import time
import urllib
import unittest

from openlibrary.coverstore import config, disk, schema, code, coverlib, utils, archive
import _setup

def setup_module(mod):
    _setup.setup_module(mod, db=True)
    mod.app = code.app
    
def teardown_module(mod):
    _setup.teardown_module(mod)
    
class WebTestCase(unittest.TestCase):
    def setUp(self):
        db.delete('cover', where='1=1')
        self.browser = app.browser()

    def jsonget(self, path):
        self.browser.open(path)
        return simplejson.loads(self.browser.data)

    def upload(self, olid, path):
        """Uploads an image in static dir"""
        b = self.browser

        path = os.path.join(static_dir, path)
        content_type, data = utils.urlencode({'olid': olid, 'file': open(path), 'failure_url': '/failed'}) 
        b.open('/b/upload', data, {'Content-Type': content_type})
        return self.jsonget('/b/olid/%s.json' % olid)['id']

    def delete(self, id, redirect_url=None):
        b = self.browser

        params = {'id': id}
        if redirect_url:
            params['redirect_url'] = redirect_url
        b.open('/b/delete', urllib.urlencode(params))
        return b.data
    
    def static_path(self, path):
        return os.path.join(static_dir, path)
        
        
class DBTest:
    def setUp(self):
        db.delete('cover', where='1=1')

    def test_write(self):
        path = static_dir + "/logos/logo-en.png"
        data = open(path).read()
        d = coverlib.save_image(data, category='b', olid='OL1M')
        
        assert 'OL1M' in d.filename
        path = config.data_root + '/localdisk/' + d.filename
        assert open(path).read() == data

class TestWebapp(WebTestCase):
    def test_touch(self):
        b = self.browser

        id1 = self.upload('OL1M', 'logos/logo-en.png')
        time.sleep(1)
        id2 = self.upload('OL1M', 'logos/logo-it.png')
        
        assert id1 < id2

        assert b.open('/b/olid/OL1M.jpg').read() == open(static_dir + '/logos/logo-it.png').read()

        b.open('/b/touch', urllib.urlencode({'id': id1}))
        assert b.open('/b/olid/OL1M.jpg').read() == open(static_dir + '/logos/logo-en.png').read()

    def test_delete(self):
        b = self.browser
        
        id1 = self.upload('OL1M', 'logos/logo-en.png')
        data = self.delete(id1)
        assert data == 'cover has been deleted successfully.'
    
    def test_get(self):
        assert app.request('/').status == "200 OK"

    def test_upload(self):
        b = self.browser

        path = os.path.join(static_dir, 'logos/logo-en.png')
        content_type, data = utils.urlencode({'olid': 'OL1234M', 'file': open(path), 'failure_url': '/failed'}) 
        b.open('/b/upload', data, {'Content-Type': content_type})

        assert b.status == 200
        assert b.path == '/'

        b.open('/b/olid/OL1234M.json')

        response = b.open('/b/olid/OL1234M.jpg')
        assert b.status == 200
        assert response.info().getheader('Content-Type') == 'image/jpeg'
        assert b.data == open(path).read()

        b.open('/b/olid/OL1234M-S.jpg')
        assert b.status == 200

        b.open('/b/olid/OL1234M-M.jpg')
        assert b.status == 200

        b.open('/b/olid/OL1234M-L.jpg')
        assert b.status == 200
        
    def test_archive_status(self):
        id = self.upload('OL1M', 'logos/logo-en.png')
        d = self.jsonget('/b/id/%d.json' % id)
        assert d['archived'] == False
        assert d['deleted'] == False

    def test_archive(self):
        b = self.browser
        
        f1 = web.storage(olid='OL1M', filename='logos/logo-en.png')
        f2 = web.storage(olid='OL2M', filename='logos/logo-it.png')
        files = [f1, f2]
        
        for f in files:
            f.id = self.upload(f.olid, f.filename)
            f.path = os.path.join(static_dir, f.filename)
            assert b.open('/b/id/%d.jpg' % f.id).read() == open(f.path).read()
        
        archive.archive()
        
        for f in files:
            d = self.jsonget('/b/id/%d.json' % f.id)
            print f.id, d
            assert 'tar:' in d['filename']
            assert b.open('/b/id/%d.jpg' % f.id).read() == open(f.path).read()
        
class TestAppWithHTTP(WebTestCase):
    def setUp(self):
        WebTestCase.setUp(self)
        
        from openlibrary.utils import httpserver
        self.server = httpserver.HTTPServer(port=8090)
        
    def tearDown(self):
        WebTestCase.tearDown(self)
        self.server.stop()
        
    def test_download(self):        
        data = open(static_dir + '/logos/logo-en.png').read()
        self.server.request('/a.png').should_return(data, headers={'Content-Type': 'image/png'})
        print self.server.mappings, self.server.t, self.server.port
        
        assert utils.download('http://0.0.0.0:8090/a.png') == data
        
    def test_upload_from_url(self):
        return
        data = open(static_dir + '/logos/logo-en.png').read()
        self.server.request('/a.png').should_return(data, headers={'Content-Type': 'image/png'})
        
        query = urllib.urlencode({'source_url': 'http://0.0.0.0:8090/a.png', 'olid': 'OL1M'})
        self.browser.open('/b/upload', query)
        
        assert self.browser.open('/b/olid/OL1M.jpg').read() == data

        d = self.jsonget('/b/olid/OL1M.json')
        assert d['source_url'] == 'http://0.0.0.0:8090/a.png'

    def test_isbn(self):
        config.things_api_url = "http://127.0.0.1:8090/api/things"
        from openlibrary.utils import httpserver

        q = {'type': '/type/edition', 'isbn_10': '1234567890', 'sort': 'last_modified', 'limit': 10}
        self.server.request('/api/things', method='GET', query={'query': simplejson.dumps(q)}).should_return('{"result":["/b/OL1M"]}')

        id = self.upload('OL1M', 'logos/logo-en.png')

        b = self.browser
        assert b.open('/b/isbn/1234567890.jpg').read() == open(os.path.join(static_dir, 'logos/logo-en.png')).read()
        
