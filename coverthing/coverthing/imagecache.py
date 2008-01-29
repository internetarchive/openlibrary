"""
Image cache for managing images.
"""

import os

import config

def populate_cache(store, id, file=None):
    """Populates cache with images of the given id."""
    if os.path.exists(_imgpath(id, 'small')):
        return
    else:
        if file is None:
            result = store.get(id, ['image'])
            if result is None:
                web.notfound()
                raise StopIteration

            file = result['image']

        _write(_imgpath(id, 'original'), file.data)
        for size in config.image_sizes:
            _create_thumbnail(id, size)
        # after creating thumbnails, the original image is not required.
        os.remove(_imgpath(id, 'original'))
        
def get_image(store, id, size):
    """Returns thumbnail of the specified size for the image specified by the id."""
    populate_cache(store, id)
    return open(_imgpath(id, size)).read()
    
def _create_thumbnail(id, size_label):
    thumbnail(_imgpath(id, 'original'), _imgpath(id, size_label), config.image_sizes[size_label])
    _increment_image_count()    

def _imgpath(id, size):
    return '%s/%d-%s.jpg' % (config.cache_dir, id, size)

def _write(filename, data):
    if not os.path.exists(os.path.dirname(filename)):
        os.makedirs(os.path.dirname(filename))

    f = open(filename, 'w')
    f.write(data)
    f.close()

_image_count = None
def _get_image_count():
    if _image_count is None:
        global _image_count
        _image_count = len(os.listdir(config.cache_dir))
    return _image_count

def _increment_image_count():
    global _image_count
    _get_image_count() # ensure initialization
    
    _image_count += 1
    _prune_cache()
        
def _prune_cache():
    def remove(f):
        try:
            os.remove(f)
        except:
            pass
    
    global _image_count
    if _image_count > 1.5 * config.cache_size:
        files = [os.path.join(config.cache_dir, f) for f in os.listdir(config.cache_dir)]
        files.sort(key=lambda f: os.stat(f).st_atime, reverse=True)
        for f in files[config.cache_size:]:
            remove(f)    
        _image_count = len(os.listdir(config.cache_dir))
    
# image engine

_engine = None

def get_image_engine():
    global _engine
    if _engine == None:
        engines = dict(pil=PIL, imagemagick=ImageMagick)
        if config.image_engine not in engines:
            raise Exception, 'Unknown image engine: ' + config.image_engine
        _engine = engines[config.image_engine]()
    return _engine
    
def thumbnail(src, dest, size):
    return get_image_engine().thumbnail(src, dest, size)

def mimetype(filename):
    return get_image_engine().mimetype(filename)

class PIL:
    """Image engine using PythonImagingLibrary."""

    def thumbnail(self, src_file, dest_file, size):
        """Converts src image to thumnail of specified size."""
        import Image
        image = Image.open(src_file)
        image.thumbnail(size)
        image.save(dest_file)
        
    def mimetype(self, filename):
        import Image
        image = Image.open(src_file)
        types = dict(JPEG='image/jpeg', GIF='image/gif')
        return types.get(image.format, 'application/octet-stream')

class ImageMagick:
    """Image engine using ImageMagick commands."""
    def thumbnail(self, src_file, dest_file, size):
        size = '%sx%s' % size
        cmd = 'convert -size %s -thumbnail %s %s %s' % (size, size, src_file, dest_file)
        os.system(cmd)
        
    def mimetype(self, filename):
        # TODO
        return 'application/octet-stream'
        
