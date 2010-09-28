"""
LRU cache implementation on disk for storing images.
"""

import os
import time
import config
import web

import db

NBLOCKS = 10000
BLOCK_SIZE = 100
OVERLOAD_FACTOR = 1.25

class ImageCache:
    """LRU cache implementation on disk for storing images.
    """
    def __init__(self, root, disk):
        self.root = root
        self.disk = disk
        self.engine = self._create_image_engine()
        # access times
        self.atimes = _BlockDict(NBLOCKS)
        self._setup()
        
    def _setup(self):
        # create all directories
        for i in range(NBLOCKS):
            d = self._dirname(i)
            if not os.path.exists(d):
                os.makedirs(d)
                            
    def _create_image_engine(self):
        engines = dict(pil=PIL, imagemagick=ImageMagick)
        if config.image_engine not in engines:
            raise Exception, 'Unknown image engine: ' + config.image_engine
        return engines[config.image_engine]()
                        
    def get_image(self, id, size):
        """Returns image with the specified id in the specified size."""
        if self.populate_cache(id):
            self.atimes[id] = time.time()
            return self._imgpath(id, size)
        
    def populate_cache(self, id):
        """Populates cache with images of the given id."""
        def write(path, data):
            #print >> web.debug, 'write', path
            f = open(path, 'w')
            f.write(data)
            f.close()
            
        if id not in self.atimes:
            # Lazily add entry to atimes if the file exists
            # Doing this lazily saves lot of startup time.
            path = self._imgpath(id, 'S')
            if os.path.exists(path):
                self.atimes[id] = time.time()
                return True

            # get the original image
            filename = db.get_filename(id)
            if filename is None:
                return False
            
            # prune the folder if it has more files    
            block_number = id % NBLOCKS
            self._prune(block_number)
            
            write(self._imgpath(id, 'original'), self.disk.read(filename))
            
            # create thumbnails
            for size in config.image_sizes:
                self.engine.thumbnail(self._imgpath(id, 'original'), self._imgpath(id, size), config.image_sizes[size])    
            
            # remove original
            os.remove(self._imgpath(id, 'original'))
            self.atimes[id] = time.time()
            
        return True

    def _imgpath(self, id, size):
        return os.path.join(self._dirname(id), '%d-%s.jpg' % (id, size))

    def _delete_images(self, id):
        for size in config.image_sizes:
            path = self._imgpath(id, size)
            try:
                os.remove(path)
            except:
                pass
        del self.atimes[id]    
        
    def _prune(self, block_number):
        block = self.atimes.get_block(block_number)
        threshold = int(OVERLOAD_FACTOR * BLOCK_SIZE)
        if len(block) > threshold:
            # other process could be updating the imagecache. 
            # update the atimes to remove the real unused files.
            self.atimes[block_number] = self.get_atimes(block_number)

            ids = sorted(block.keys(), key=lambda id: block[id], reverse=True)
            for id in ids[BLOCK_SIZE:]:
                self._delete_images(id)
                
    def get_atimes(block_number):
        atimes = {}
        d = self._dirname(block_number) # _dirname works even with block_number
        for f in os.listdir(d):
            id = int(web.numify(f))
            atime = os.stat(os.path.join(d, f)).st_atime
            atimes[id] = max(self.atimes.get(id, 0), atime)
        return atimes
        
    def _dirname(self, id):
        block = "%04d" % (id % NBLOCKS)
        a, b = block[:2], block[2:]
        return os.path.join(self.root, a, b)

class _BlockDict:
    """A dictionary with integer keys to use with ImageCache.
    
    Values can be accessed just like normal dictionary and also blockwise.
    Keys are grouped into blocks. Key i belongs to block number i % nblocks.
    """
    def __init__(self, nblocks):
        self.nblocks = nblocks
        self.data = [{} for i in range(nblocks)]
        
    def __getitem__(self, i):
        block = i % self.nblocks
        return self.data[block][i]
        
    def __setitem__(self, i, value):
        block = i % self.nblocks
        self.data[block][i] = value
        
    def __delitem__(self, i):
        block = i % self.nblocks
        del self.data[block][i]
        
    def __contains__(self, i):
        block = i % self.nblocks
        return i in self.data[block]
        
    def get(self, i, default=None):
        block = i % self.nblocks
        return self.data[block].get(i, default)
        
    def get_block(self, block_number):
        """Returns the dictionary for the specified block."""
        return self.data[block_number]
    
class PIL:
    """Image engine using PythonImagingLibrary."""

    def thumbnail(self, src_file, dest_file, size):
        """Converts src image to thumnail of specified size."""
        #print >> web.debug, 'thumbnail', src_file, dest_file
        import Image
        image = Image.open(src_file)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        image.thumbnail(size, resample=Image.ANTIALIAS)
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
