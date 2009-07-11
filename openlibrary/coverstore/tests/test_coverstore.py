import py.test
import os.path
import web

from openlibrary.coverstore import config, disk, schema, code, utils
import setup

def setup_module(mod):
    setup.setup_module(mod, db=False)
    
    mod.root.mkdir('items', 'covers_0000')
    mod.root.mkdir('items', 's_covers_0000')
    mod.root.mkdir('items', 'm_covers_0000')
    mod.root.mkdir('items', 'l_covers_0000')
    
def teardown_module(mod):
    setup.teardown_module(mod)

def test_write_image():
    yield _test_write_image, 'a', static_dir + '/images/ajaxImage.jpg'
    yield _test_write_image, 'b', static_dir + '/logos/logo-en.gif'
    yield _test_write_image, 'c', static_dir + '/logos/logo-en.png'
        
def _test_write_image(prefix, path):
    data = open(path).read()
    assert code.write_image(data, prefix) != None
    
    def exists(filename):
        return os.path.exists(code.find_image_path(filename))
    
    assert exists(prefix + '.jpg')
    assert exists(prefix + '-S.jpg')
    assert exists(prefix + '-M.jpg')
    assert exists(prefix + '-L.jpg')
    
    assert open(code.find_image_path(prefix + '.jpg')).read() == data

def test_bad_image():
    prefix = config.data_root + '/bad'
    assert code.write_image('', prefix) == None

    prefix = config.data_root + '/bad'
    assert code.write_image('not an image', prefix) == None

def test_serve_file():
    path = static_dir + "/logos/logo-en.png"
        
    assert code.serve_file('/dev/null') == ''
    assert code.serve_file(path) == open(path).read()

    assert code.serve_file(path + ":10:20") == open(path).read()[10:10+20] 
    
def test_server_image():
    def write(filename, data):
        f = open(os.path.join(config.data_root, filename), 'w')
        f.write(data)
        f.close()

    def do_test(d):
        def serve_image(d, size):
            return "".join(code.serve_image(d, size))

        assert serve_image(d, '') == 'main image'
        assert serve_image(d, None) == 'main image'    

        assert serve_image(d, 'S') == 'S image'
        assert serve_image(d, 'M') == 'M image'
        assert serve_image(d, 'L') == 'L image'

        assert serve_image(d, 's') == 'S image'
        assert serve_image(d, 'm') == 'M image'
        assert serve_image(d, 'l') == 'L image'
        
    write('localdisk/a.jpg', 'main image')
    write('localdisk/a-S.jpg', 'S image')
    write('localdisk/a-M.jpg', 'M image')
    write('localdisk/a-L.jpg', 'L image')
    
    d = web.storage(filename='a.jpg', filename_s='a-S.jpg', filename_m='a-M.jpg', filename_l='a-L.jpg')
    do_test(d)
    
    write('items/covers_0000/covers_0000_00.tar', 'xxmain imagexx')
    write('items/s_covers_0000/s_covers_0000_00.tar', 'xxS imagexx')
    write('items/m_covers_0000/m_covers_0000_00.tar', 'xxM imagexx')
    write('items/l_covers_0000/l_covers_0000_00.tar', 'xxL imagexx')

    d = web.storage(
        filename='covers_0000_00.tar:2:10', 
        filename_s='s_covers_0000_00.tar:2:7', 
        filename_m='m_covers_0000_00.tar:2:7',
        filename_l='l_covers_0000_00.tar:2:7')
    do_test(d)

def test_image_path():
    assert code.find_image_path('a.jpg') == config.data_root + '/localdisk/a.jpg'
    assert code.find_image_path('covers_0000_00.tar:1234:10') == config.data_root + '/items/covers_0000/covers_0000_00.tar:1234:10'
