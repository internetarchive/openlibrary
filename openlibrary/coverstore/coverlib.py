"""Cover management."""

import Image
import os
from cStringIO import StringIO
import web
import datetime

import config
import db
from utils import random_string, rm_f

__all__ = [
    "save_image",
    "read_image",
    "read_file"
]

def save_image(data, category, olid, author=None, ip=None, source_url=None):
    """Save the provided image data, creates thumbnails and adds an entry in the database.
    
    ValueError is raised if the provided data is not a valid image.
    """
    prefix = make_path_prefix(olid)
    
    img = write_image(data, prefix)
    if img is None:
        raise ValueError("Bad Image")

    d = web.storage({
        'category': category,
        'olid': olid,
        'author': author,
        'source_url': source_url,
    })
    d['width'], d['height'] = img.size

    filename = prefix + '.jpg'
    d['ip'] = ip
    d['filename'] = filename
    d['filename_s'] = prefix + '-S.jpg'
    d['filename_m'] = prefix + '-M.jpg'
    d['filename_l'] = prefix + '-L.jpg'
    d.id = db.new(**d)
    return d
    
def make_path_prefix(olid, date=None):
    """Makes a file prefix for storing an image.
    """
    date = date or datetime.date.today()
    return "%04d/%02d/%02d/%s-%s" % (date.year, date.month, date.day, olid, random_string(5))
    
def write_image(data, prefix):
    path_prefix = find_image_path(prefix)
    dirname = os.path.dirname(path_prefix)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    try:
        # save original image
        f = open(path_prefix + '.jpg', 'w')
        f.write(data)
        f.close()

        img = Image.open(StringIO(data))
        if img.mode != 'RGB':
            img = img.convert('RGB')

        for name, size in config.image_sizes.items():
            path = "%s-%s.jpg" % (path_prefix, name)
            resize_image(img, size).save(path)
        return img
    except IOError, e:
        print 'ERROR:', str(e)

        # cleanup
        rm_f(prefix + '.jpg')
        rm_f(prefix + '-S.jpg')
        rm_f(prefix + '-M.jpg')
        rm_f(prefix + '-L.jpg')

        return None

def resize_image(image, size):
    """Resizes image to specified size while making sure that aspect ratio is maintained."""
    # from PIL
    x, y = image.size
    if x > size[0]: y = max(y * size[0] / x, 1); x = size[0]
    if y > size[1]: x = max(x * size[1] / y, 1); y = size[1]
    size = x, y

    return image.resize(size, Image.ANTIALIAS)

def find_image_path(filename):
    if ':' in filename: 
        return os.path.join(config.data_root,'items', filename.rsplit('_', 1)[0], filename)
    else:
        return os.path.join(config.data_root, 'localdisk', filename)

def read_file(path):
    if ':' in path:
        path, offset, size = path.rsplit(':', 2)
        offset = int(offset)
        size = int(size)
        f = open(path)
        f.seek(offset)
        data = f.read(size)
        f.close()
    else:
        f = open(path)
        data = f.read()
        f.close()
    return data

def read_image(d, size):
    if size:
        filename = d['filename_' + size.lower()] or d.filename + "-%s.jpg" % size.upper()
    else:
        filename = d.filename
    path = find_image_path(filename)
    return read_file(path)
