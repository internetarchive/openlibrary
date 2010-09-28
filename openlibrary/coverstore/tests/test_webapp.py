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
    
def pytest_funcarg__foo(request):
    return "foo"
    
def test_foo(foo):
    assert foo == "foo"

class Mock:
    def __init__(self):
        self.calls = []
        self.default = None

    def __call__(self, *a, **kw):
        for a2, kw2, _return in self.calls:
            if (a, kw) == (a2, kw2):
                return _return
        return self.default

    def setup_call(self, *a, **kw):
        _return = kw.pop("_return", None)
        call = a, kw, _return
        self.calls.append(call)
    
class WebTestCase:
    def setup_method(self, method):
        db.delete("log", where="1=1")
        db.delete('cover', where='1=1')
        self.browser = app.browser()

    def jsonget(self, path):
        self.browser.open(path)
        return simplejson.loads(self.browser.data)

    def upload(self, olid, path):
        """Uploads an image in static dir"""
        b = self.browser

        path = os.path.join(static_dir, path)
        content_type, data = utils.urlencode({'olid': olid, 'data': open(path).read()}) 
        b.open('/b/upload2', data, {'Content-Type': content_type})
        return simplejson.loads(b.data)['id']

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
        py.test.skip("TODO: touch is no more used. Remove or fix this test later.")
        
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
        filedata = open(path).read()
        content_type, data = utils.urlencode({'olid': 'OL1234M', 'data': filedata}) 
        b.open('/b/upload2', data, {'Content-Type': content_type})
        id = simplejson.loads(b.data)['id']

        assert b.status == 200
        self.verify_upload(id, filedata, {'olid': 'OL1234M'})
        
    def test_upload_with_url(self, monkeypatch):
        filedata = open(static_dir + '/logos/logo-en.png').read()
        source_url = "http://example.com/bookcovers/1.jpg"
        
        mock = Mock()
        mock.setup_call(source_url, _return=filedata)
        monkeypatch.setattr(code, "download", mock)
        monkeypatch.setattr(utils, "download", mock)
        
        content_type, data = utils.urlencode({'olid': 'OL1234M', 'source_url': source_url}) 
        self.browser.open('/b/upload2', data, {'Content-Type': content_type})
        
        print "data", self.browser.data
        
        id = simplejson.loads(self.browser.data)['id']
        self.verify_upload(id, filedata, {"source_url": source_url, "olid": "OL1234M"})

    def verify_upload(self, id, data, expected_info={}):
        b = self.browser
        b.open('/b/id/%d.json' % id)
        info = simplejson.loads(b.data)
        for k, v in expected_info.items():
            assert info[k] == v

        response = b.open('/b/id/%d.jpg' % id)
        assert b.status == 200
        assert response.info().getheader('Content-Type') == 'image/jpeg'
        assert b.data == data

        b.open('/b/id/%d-S.jpg' % id)
        assert b.status == 200

        b.open('/b/id/%d-M.jpg' % id)
        assert b.status == 200

        b.open('/b/id/%d-L.jpg' % id)
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
