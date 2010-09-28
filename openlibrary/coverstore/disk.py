import random
import os
import string
import warc

chars = string.letters + string.digits
def random_string(n):
    return "".join([random.choice(chars) for i in range(n)])

class Disk:
    """Disk interface to store files.

    >>> import os, string
    >>> _ = os.system("rm -rf test_disk")
    >>> disk = Disk("test_disk")
    >>> f1 = disk.write("hello, world!")
    >>> f2 = disk.write(string.letters)
    >>> f3 = disk.write(string.letters)
    >>> disk.read(f1)
    'hello, world!'
    >>> disk.read(f2)
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    >>> disk.read(f3)
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    """
    def __init__(self, root):
        self.root = root
        if not os.path.exists(root):
            os.makedirs(root)

    def write(self, data, params={}):
        prefix = params.get('olid', '')
        filename = self.make_filename(prefix)
        path = os.path.join(self.root, filename)
        f = open(path, 'w')
        f.write(data)
        f.close()
        return filename

    def read(self, filename):
        path = os.path.join(self.root, filename)
        if os.path.exists(path):
            return open(path).read()
        
    def make_filename(self, prefix=""):
        def exists(filename):
            return os.path.exists(os.path.join(self.root, filename))
        filename = prefix + "_" + random_string(4)
        while exists(filename):
            filename = prefix + "_"  + random_string(4)
        return filename

class WARCDisk:
    def __init__(self, root, prefix="file", maxsize=500 * 1024 * 1024):
        """Creates a disk to write read and write resources in warc files.

        WARNING: This class is not thread-safe. Multiple threads trying to write at the same time may result in race-conditions.

        >>> import os, string
        >>> _ = os.system("rm -rf test_disk")
        >>> disk = WARCDisk("test_disk", maxsize=200)
        >>> f1 = disk.write("hello, world!")
        >>> f2 = disk.write(string.letters)
        >>> f3 = disk.write(string.letters)
        >>> disk.read(f1)
        'hello, world!'
        >>> disk.read(f2)
        'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
        >>> disk.read(f3)
        'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
        """
        # this is required for warc.WARCRecord. Testing to fail early.
        import uuid

        self.root = root
        if not os.path.exists(root):
            os.makedirs(root)

        self.next_warcfile = None
        self.maxsize = maxsize
        self.warcfile_prefix = prefix

    def get_item_name(self, warcfilename):
        # warc file file_xxxx_yy.warc is stored in item file_xxxx.
        itemname, _ = warcfilename.rsplit('_', 1)
        return itemname

    def read(self, filename):
        if filename.count(':') != 2:
            return None
        warcfilename, offset, size = filename.split(':')
        offset = int(offset)
        size = int(size)
        path = self.get_path(warcfilename)
        if os.path.exists(path):
            f = open(path)
            f.seek(offset)
            return f.read(size)

    def get_path(self, warcfilename, create_dirs=False):
        dir = os.path.join(self.root, self.get_item_name(warcfilename))
        if create_dirs and not os.path.exists(dir):
            os.mkdir(dir)
        return os.path.join(dir, warcfilename)

    def write(self, data, headers={}):
        warcfilename = self.get_next_warcfile()
        path = self.get_path(warcfilename, create_dirs=True)
        w = warc.WARCWriter(open(path, 'a'))

        headers = dict(headers)
        subject_uri = headers.pop('subject_uri', 'xxx')
        mimetype = headers.pop('mimetype', 'application/octet-stream')
        
        warc_record = warc.WARCRecord('resource', subject_uri, mimetype, headers, data)
        offset = w.write(warc_record)
        w.close()
        filename = '%s:%d:%d' % (warcfilename, offset, len(data))
        return filename

    def find(self, dir):
        """Find all files in the given directory."""
        for dirpath, dirnames, filenames in os.walk(dir):
            for f in filenames:
                yield os.path.join(dirpath, f)

    def get_next_warcfile(self):
        """Find the next warc file.
        
        For a new disk, next_warcfile should be file_0000_00.warc.
        
            >>> import os, string
            >>> _ = os.system("rm -rf test_disk")
            >>> disk = WARCDisk("test_disk", maxsize=100)
            >>> disk.get_next_warcfile()
            'file_0000_00.warc'
            
        After writing enough data, it should move to next file.
        
            >>> _ = disk.write('x' * 100)
            >>> disk.get_next_warcfile()
            'file_0000_01.warc'
            
        A a new disk with existing data should be able to find the correct value of next_warcfile.
        
            >>> disk = WARCDisk("test_disk", maxsize=100)
            >>> disk.get_next_warcfile()
            'file_0000_01.warc'
        """
        from web.utils import numify, denumify
    
        #@@ this could be dangerous. If we clear the directory, it starts again from count 0. 
        #@@ Probably, this should be taken from database.
        if self.next_warcfile is None:
            files = [os.path.basename(f) for f in self.find(self.root) if f.endswith('.warc')]
            if files:
                files.sort()
                self.next_warcfile = files[-1]
            else:
                self.next_warcfile = self.warcfile_prefix + '_0000_00.warc'

        path = self.get_path(self.next_warcfile)
        if os.path.exists(path) and self.filesize(path) >= self.maxsize:
            count = int(numify(self.next_warcfile)) + 1
            self.next_warcfile = self.warcfile_prefix + denumify("%06d" % count, "_XXXX_XX.warc")

        return self.next_warcfile

    def filesize(self, filename):
        return os.stat(filename).st_size

class ArchiveDisk(WARCDisk):
    """Disk interface to internet archive storage.
    
    There is a convention that is used to name files and items. 
    prefix_xxxx_yy.ext is saved in item named prefix_xxxx.
    """
    def make_warcfile(self, warcfilename):
        path = self.get_path(warcfilename)
        if os.path.exists(path):
            return open(path)
        else:
            itemname = self.get_item_name(warcfilename)
            url = self.item_url(itemname) + '/' + warcfilename
            return warc.HTTPFile(url)
    
    def read(self, filename):
        # if the file is locally available then read it from there.
        # else contact the server
        try:
            data = WARCDisk.read(self, filename)
        except IOError:
            data = None

        if data:
            return data

        warcfilename, offset, size = filename.split(':')
        offset = int(offset)
        size = int(size)
        f = self.make_warcfile(warcfilename)
        f.seek(offset)
        return f.read(size)

    def create_file(filename):
        itemname = self.get_item_name(filename)
        url = self.item_url(itemname) + '/' + filename
        return warc.HTTPFile(url)

    def get_item_name(self, warcfilename):
        # warc file file_xxxx_yy.warc is stored in item file_xxxx.
        itemname, _ = warcfilename.rsplit('_', 1)
        return itemname

    def item_url(self, itemname):
        """Returns http url to access files from the item specified by the itemname."""
        from xml.dom import minidom
        import urllib
        base_url = 'http://www.archive.org/services/find_file.php?loconly=1&file='
        try:
            data= urllib.urlopen(base_url + itemname).read()
            doc = minidom.parseString(data)
            vals = ['http://' + e.getAttribute('host') + e.getAttribute('dir') for e in doc.getElementsByTagName('location')]
            return vals and vals[0]
        except Exception:
            return None
  
class LayeredDisk:
    """Disk interface over multiple disks.
    Write always happens to the first disk and 
    read happens on the first disk where the file is available.
    """
    def __init__(self, disks):
        self.disks = disks
        
    def read(self, filename):
        for disk in self.disks:
            data = disk.read(filename)
            if data:
                return data
        
    def write(self, data, headers={}):
        return self.disks[0].write(data, headers)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
    
