import pytest
from os.path import abspath, exists, join, dirname, pardir
import web

from openlibrary.coverstore import config, coverlib, disk, schema, utils

static_dir = abspath(join(dirname(__file__), pardir, pardir, pardir, 'static'))

image_formats = [
    ['a', 'images/homesplash.jpg'],
    ['b', 'logos/logo-en.gif'],
    ['c', 'logos/logo-en.png']
]

@pytest.fixture
def image_dir(tmpdir):
    tmpdir.mkdir('localdisk')
    tmpdir.mkdir('items')
    tmpdir.mkdir('items', 'covers_0000')
    tmpdir.mkdir('items', 's_covers_0000')
    tmpdir.mkdir('items', 'm_covers_0000')
    tmpdir.mkdir('items', 'l_covers_0000')

    config.data_root = str(tmpdir)

@pytest.mark.parametrize('prefix, path', image_formats)
def test_write_image(prefix, path, image_dir):
    """Test writing jpg, gif and png images"""
    data = open(join(static_dir, path)).read()
    assert coverlib.write_image(data, prefix) is not None

    def _exists(filename):
        return exists(coverlib.find_image_path(filename))

    assert _exists(prefix + '.jpg')
    assert _exists(prefix + '-S.jpg')
    assert _exists(prefix + '-M.jpg')
    assert _exists(prefix + '-L.jpg')

    assert open(coverlib.find_image_path(prefix + '.jpg')).read() == data

def test_bad_image(image_dir):
    prefix = config.data_root + '/bad'
    assert coverlib.write_image('', prefix) == None

    prefix = config.data_root + '/bad'
    assert coverlib.write_image('not an image', prefix) == None

def test_resize_image_aspect_ratio():
    """make sure the aspect-ratio is maintained"""
    from PIL import Image
    img = Image.new('RGB', (100, 200))

    img2 = coverlib.resize_image(img, (40, 40))
    assert img2.size == (20, 40)

    img2 = coverlib.resize_image(img, (400, 400))
    assert img2.size == (100, 200)

    img2 = coverlib.resize_image(img, (75, 100))
    assert img2.size == (50, 100)

    img2 = coverlib.resize_image(img, (75, 200))
    assert img2.size == (75, 150)

def test_serve_file(image_dir):
    path = static_dir + "/logos/logo-en.png"

    assert coverlib.read_file('/dev/null') == ''
    assert coverlib.read_file(path) == open(path).read()

    assert coverlib.read_file(path + ":10:20") == open(path).read()[10:10+20]

def test_server_image(image_dir):
    def write(filename, data):
        f = open(join(config.data_root, filename), 'w')
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

def test_image_path(image_dir):
    assert coverlib.find_image_path('a.jpg') == config.data_root + '/localdisk/a.jpg'
    assert coverlib.find_image_path('covers_0000_00.tar:1234:10') == config.data_root + '/items/covers_0000/covers_0000_00.tar:1234:10'
