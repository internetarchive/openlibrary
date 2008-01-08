"""Disk: interface to store files."""
import os.path
import web
import urllib
import re

import warc

class File:
    def __init__(self, data, mimetype='application/octet-stream', headers=None):
        self._data = data
        self.mimetype = mimetype
        self.headers = headers or {}
        
    def _getdata(self):
        # _data can be a function to initialize data lazily.
        if hasattr(self._data, '__call__'):
            self._data = self._data()
        return self._data
        
    data = property(_getdata)

    def __eq__(self, object):
        return isinstance(object, File) and self.data == object.data
    
    def __ne__(self, other):pass

class Disk:
    def __init__(self, root):
        self.root = root

    def write(self, filename, file):
        """Writes the given file to disk and returns the saved filename.
        The file may be saved with a different name on the disk.
        """
        "Write a file to disk."
        path = os.path.join(self.root, filename)
        f = open(path, 'w')
        f.write(file.data)
        f.close()
        return filename

    def read(self, filename):
        "Reads a file from disk."
        path = os.path.join(self.root, filename)
        return File(open(path).read)

class WARCDisk:
    def __init__(self, root, prefix="file", maxsize=500 * 1024 * 1024):
        """Creates a disk to write read and write resources in warc files.
        """
        # this is required for warc.WARCRecord. Testing to fail early.
        import uuid

        self.root = root
        self.next_warcfile = None
        self.maxsize = maxsize
        self.warcfile_prefix = prefix
        
    def get_item_name(self, warcfilename):
        # warc file file_xxxx_yy.warc is stored in item file_xxxx.
        itemname, _ = warcfilename.rsplit('_', 1)
        return itemname
    
    def read(self, filename):
        warcfilename, offset, size = filename.split(':')
        offset = int(offset)
        size = int(size)
        path = self.get_path(warcfilename)
        f = open(path)
        f.seek(offset)
        return File(lambda: f.read(size))
        
    def get_path(self, warcfilename, create_dirs=False):
        dir = os.path.join(self.root, self.get_item_name(warcfilename))
        if create_dirs and not os.path.exists(dir):
            os.mkdir(dir)
        return os.path.join(dir, warcfilename)

    def write(self, filename, file):
        warcfilename = self.get_next_warcfile()
        path = self.get_path(warcfilename, create_dirs=True)
        w = warc.WARCWriter(open(path, 'a'))

        subject_uri = filename
        warc_record = warc.WARCRecord('resource', subject_uri, file.mimetype, file.headers, file.data)
        offset = w.write(warc_record)
        w.close()
        filename = '%s:%d:%d' % (warcfilename, offset, len(file.data))
        print 'write', filename
        return filename
        
    def find(self, dir):
        """Find all files in the given directory."""
        for dirpath, dirnames, filenames in os.walk(dir):
            for f in filenames:
                yield os.path.join(dirpath, f)
    
    def get_next_warcfile(self):
        #@@ this is dangerous. If we clear the directory, it starts again from count 0. 
        #@@ Probably, this should be taken from database.
        if self.next_warcfile is None:
            files = [os.path.basename(f) for f in self.find(self.root) if f.endswith('.warc')]
            if files:
                files.sort()
                self.next_warcfile = files[-1]
            else:
                self.next_warcfile = self.warcfile_prefix + '_0000_00.warc'
        
        path = self.get_path(self.next_warcfile)
        if os.path.exists(path) and self.filesize(path) > self.maxsize:
            count = int(web.numify(self.next_warcfile)) + 1
            self.next_warcfile = self.warcfile_prefix + web.denumify("%06d" % count, "_XXXX_XX.warc")
            
        return self.next_warcfile

    def filesize(self, filename):
        return os.stat(filename).st_size

class ArchiveDisk(WARCDisk):
    """Disk interface to internet archive storage.
    
    There is a convention that is used to name files and items. 
    prefix_xxxx_yy.ext is saved in item named prefix_xxxx.
    
    The constructor expects a upload function, which is called with 
    itemname and filename as arguments to upload a file to archive storage.
    """
    def __init__(self, upload_func, root, prefix="file", maxsize=500 * 1024 * 1024):
        WARCDisk.__init__(self, root, prefix, maxsize)
        self.upload = upload_func
    
    def write(self, filename, data, headers={}):
        fileid = WARCDisk.write(self, filename, data, headers)
        warcfilename = fileid.split(':')[0]
        itemname = self.get_item_name(warcfilename)
        self.upload(itemname, warcfilename)
        return fileid
        
    def read(self, filename):
        warcfilename, offset, size = self.index[filename]
        itemname = self.get_item_name(warcfilename)
        url = self.item_url(itemname) + '/' + warcfilename
        f = warc.HTTPFile(url)
        f.seek(offset)
        #@ what about mimetype?
        return File(lambda: f.read(size))

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
        result = urllib.urlopen('http://archive.org/details/' + itemname).read()
        urls =  re.findall(r'(?:http|ftp)://ia[0-9]*.us.archive.org/[0-9]*/items/' + itemname, result)
        return urls[0].replace('ftp://', 'http://')
