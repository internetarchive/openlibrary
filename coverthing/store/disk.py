"""Disk: interface to store files."""
import os.path
import warc
import urllib
import re

class Disk:
    def __init__(self, root):
        self.root = root

    def write(self, filename, data, headers={}):
        "Write a file to disk."
        path = os.path.join(self.root, filename)
        f = open(path, 'w')
        f.write(data)
        f.close()

    def read(self, filename):
        "Reads a file from disk."
        path = os.path.join(self.root, filename)
        return open(path).read()

class WARCDisk:
    def __init__(self, root, prefix="file", maxsize=500 * 1024 * 1024):
        """Creates a disk to write read and write resources in warc files.
        """
        # this is required for warc.WARCRecord. Testing to fail early.
        import uuid

        self.root = root
        self.index_path = os.path.join(root, 'index.txt')
        self.index = self._make_index(self.index_path)
        self.next_warcfile = None
        self.maxsize = maxsize
        self.warcfile_prefix = prefix

    def _make_index(self, path):
        index = {}
        if not os.path.exists(path):
            return index

        for line in open(path).readlines():
            filename, warcfilename, offset, size = line.strip().split()
            index[filename] = warcfilename, int(offset), int(size)
        return index
        
    def update_index(self, filename, warcfilename, offset, size):
        self.index[filename] = warcfilename, offset, size
        f = open(self.index_path, 'a')
        f.write("%s %s %d %d\n" % (filename, warcfilename, offset, size))
        f.close()
        
    def read(self, filename):
        if filename not in self.index:
            raise IOError, 'No such file or directory: %s' % repr(filename)
        warcfilename, offset, size = self.index[filename]
        path = os.path.join(self.root, warcfilename)
        f = open(path)
        f.seek(offset)
        return f.read(size)
        
    def create_file(path):
        path = os.path.join(self.root, warcfilename)
        return open(path)

    def write(self, filename, data, headers={}):
        warcfilename = self.get_next_warcfile()
        path = os.path.join(self.root, warcfilename)
        w = warc.WARCWriter(open(path, 'a'))

        subject_uri = filename
        warc_record = warc.WARCRecord('resource', subject_uri, 'image/jpeg', headers, data)
        offset = w.write(warc_record)
        self.update_index(filename, warcfilename, offset, len(data))
        w.close()
    
    def get_next_warcfile(self):
        if self.next_warcfile is None:
            files = [f for f in os.listdir(self.root) if f.startswith(self.warcfile_prefix) and f.endswith('.warc')]
            if files:
                files.sort()
                self.next_warcfile = files[-1]
            else:
                self.next_warcfile = self.warcfile_prefix + '_0000_00.warc'
                
        if os.path.exists(self.next_warcfile) and self.filesize(self.next_warcfile) > self.maxsize:
            count = web.numify(self.next_warcfile) + 1
            self.next_warcfile = self.warcfile_prefix + web.denumify("%6d" % count, "_XXXX_XX.warc")
            
        return self.next_warcfile

    def filesize(filename):
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
        WARCDisk.write(self, filename, data, headers)
        warcfilename, offset, size = self.index[filename]
        itemname = self.get_item_name(warcfilename)
        self.upload(itemname, warcfilename)
        
    def read(self, filename):
        warcfilename, offset, size = self.index[filename]
        itemname = self.get_item_name(warcfilename)
        url = self.item_url(itemname) + '/' + warcfilename
        f = warc.HTTPFile(url)
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
        result = urllib.urlopen('http://archive.org/details/' + itemname).read()
        urls =  re.findall(r'(?:http|ftp)://ia[0-9]*.us.archive.org/[0-9]*/items/' + itemname, result)
        return urls[0].replace('ftp://', 'http://')
