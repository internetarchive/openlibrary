"""Open Library storage based on local files.
"""
import urllib
import os
from . import base

class LocalStorage(base.BaseStorage):
    """Open Library storage based on local files.
    """
    def __init__(self, root, base_url=None):
        """Creates a LocalStorage instance. 
        
        :param root: the storage root directory
        """
        self.root = root
        self.base_url = base_url or urllib.pathname2url(root)
        
    def find_item(self, itemid):
        path = os.path.join(self.root, itemid)
        if os.path.exists(path):
            return LocalItem(itemid=itemid, path=path, base_url=self.base_url + "/" + itemid)
        
class LocalItem(base.Item):
    def __init__(self, itemid, path, base_url):
        self.itemid = itemid
        self.path = path
        self.base_url = base_url
        
    def list_files(self):
        return os.path.listdir(self.root)
        
    def get_file(self, filename):
        path = os.path.join(self.path, filename)
        if os.path.exists(path):
            url = self.base_url + "/" + filename
            return LocalFile(path, url)
        
class LocalFile(base.File):
    def __init__(self, path, url):
        self.path = path
        self.url = url
        
    def read(self):
        return open(self.path).read()