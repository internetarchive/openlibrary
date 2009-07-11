import py.test
import os.path
import web

from openlibrary.coverstore import config, disk, schema, code, utils
import setup

def setup_module(mod):
    setup.setup_module(mod, db=True)
    mod.app = code.app
    
def teardown_module(mod):
    setup.teardown_module(mod)

def test_add():
    assert 1 + 2 == 3

def test_get():
    assert app.request('/').status == "200 OK"
    #assert app.request('/b/id/1-M.jpg').status == "404 Not Found"

def test_upload():
    path = static_dir + '/logos/logo-en.png'
    b = app.browser()
    
    content_type, data = utils.urlencode({'olid': 'OL1234M', 'file': open(path), 'failure_url': '/failed'}) 
    b.open('/b/upload', data, {'Content-Type': content_type})
    
    assert b.status == 200
    assert b.path == '/'
    
    b.open('/b/olid/OL1234M.json')
    print b.data
    
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
