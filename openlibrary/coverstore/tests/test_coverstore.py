import py.test
import os.path
import web
import unittest

from openlibrary.coverstore import config, coverlib, disk, schema, utils
import _setup

def setup_module(mod):
    _setup.setup_module(mod, db=False)
    
    mod.root.mkdir('items', 'covers_0000')
    mod.root.mkdir('items', 's_covers_0000')
    mod.root.mkdir('items', 'm_covers_0000')
    mod.root.mkdir('items', 'l_covers_0000')
    
def teardown_module(mod):
    _setup.teardown_module(mod)

def test_write_image():
    """Test writing jpg, gif and png images"""
    yield _test_write_image, 'a', static_dir + '/images/ajaxImage.jpg'
    yield _test_write_image, 'b', static_dir + '/logos/logo-en.gif'
    yield _test_write_image, 'c', static_dir + '/logos/logo-en.png'
    
def _test_write_image(prefix, path):
    data = open(path).read()
    assert coverlib.write_image(data, prefix) != None
    
    def exists(filename):
        return os.path.exists(coverlib.find_image_path(filename))
    
    assert exists(prefix + '.jpg')
    assert exists(prefix + '-S.jpg')
    assert exists(prefix + '-M.jpg')
    assert exists(prefix + '-L.jpg')
    
    assert open(coverlib.find_image_path(prefix + '.jpg')).read() == data

def test_bad_image():
    prefix = config.data_root + '/bad'
    assert coverlib.write_image('', prefix) == None

    prefix = config.data_root + '/bad'
    assert coverlib.write_image('not an image', prefix) == None
    
def test_resize_image_aspect_ratio():
    """make sure the aspect-ratio is maintained"""
    import Image
    img = Image.new('RGB', (100, 200))
    
    img2 = coverlib.resize_image(img, (40, 40))
    assert img2.size == (20, 40)

    img2 = coverlib.resize_image(img, (400, 400))
    assert img2.size == (100, 200)
    
    img2 = coverlib.resize_image(img, (75, 100))
    assert img2.size == (50, 100)
    
    img2 = coverlib.resize_image(img, (75, 200))
    assert img2.size == (75, 150)

def test_serve_file():
    path = static_dir + "/logos/logo-en.png"
        
    assert coverlib.read_file('/dev/null') == ''
    assert coverlib.read_file(path) == open(path).read()

    assert coverlib.read_file(path + ":10:20") == open(path).read()[10:10+20] 
    
def test_server_image():
    def write(filename, data):
        f = open(os.path.join(config.data_root, filename), 'w')
        f.write(data)
        f.close()

    def do_test(d):
        def serve_image(d, size):
            return "".join(coverlib.read_image(d, size))

        assert serve_image(d, '') == 'main image'
        assert serve_image(d, None) == 'main image'    

        assert serve_image(d, 'S') == 'S image'
        assert serve_image(d, 'M') == 'M image'
        assert serve_image(d, 'L') == 'L image'

        assert serve_image(d, 's') == 'S image'
        assert serve_image(d, 'm') == 'M image'
        assert serve_image(d, 'l') == 'L image'
        
    # test with regular images
    write('localdisk/a.jpg', 'main image')
    write('localdisk/a-S.jpg', 'S image')
    write('localdisk/a-M.jpg', 'M image')
    write('localdisk/a-L.jpg', 'L image')
    
    d = web.storage(id=1, filename='a.jpg', filename_s='a-S.jpg', filename_m='a-M.jpg', filename_l='a-L.jpg')
    do_test(d)
    
    # test with offsets
    write('items/covers_0000/covers_0000_00.tar', 'xxmain imagexx')
    write('items/s_covers_0000/s_covers_0000_00.tar', 'xxS imagexx')
    write('items/m_covers_0000/m_covers_0000_00.tar', 'xxM imagexx')
    write('items/l_covers_0000/l_covers_0000_00.tar', 'xxL imagexx')

    d = web.storage(
        id=1,
        filename='covers_0000_00.tar:2:10', 
        filename_s='s_covers_0000_00.tar:2:7', 
        filename_m='m_covers_0000_00.tar:2:7',
        filename_l='l_covers_0000_00.tar:2:7')
    do_test(d)

def test_image_path():
    assert coverlib.find_image_path('a.jpg') == config.data_root + '/localdisk/a.jpg'
    assert coverlib.find_image_path('covers_0000_00.tar:1234:10') == config.data_root + '/items/covers_0000/covers_0000_00.tar:1234:10'
