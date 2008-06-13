import urllib2
import xml.etree.ElementTree as et
from catalog.marc.parse import parser

archive_url = "http://archive.org/download/"

class FileWrapper(file):
    def __init__(self, part):
        self.fh = urllib2.urlopen(archive_url + part)
        self.pos = 0
    def read(self, size):
        self.pos += size
        return self.fh.read(size)
    def tell(self):
        return self.pos
    def close(self):
        return self.fh.close()

def files(id):
    url = archive_url + id + "/" + id + "_files.xml"
    tree = et.parse(urllib2.urlopen(url))
    for i in tree.getroot():
        assert i.tag == 'file'
        name = i.attrib['name']
        if name.endswith('.mrc') or name.endswith('.marc') or name.endswith('.out'):
            yield id + "/" + name

def bad_data(i):
    pass

id = "unc_catalog_marc"
id = "marc_oregon_summit_records"
id = "marc_university_of_toronto"
id = "marc_miami_univ_ohio"
id = "marc_western_washington_univ"
id = "marc_boston_college"
i = 0
for f in files(id):
    print f
    for e in parser(f, FileWrapper(f), bad_data):
        if i % 1000 == 0:
            print i, e['title']
        i+=1

print i
