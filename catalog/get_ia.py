import catalog.marc.fast_parse as fast_parse
import catalog.marc.read_xml as read_xml
import xml.etree.ElementTree as et
import xml.parsers.expat
import urllib2, os.path
from catalog.read_rc import read_rc
from time import sleep

rc = read_rc()

base = "http://archive.org/download/"

xml_path = '/home/edward/get_new_books/xml'

def urlopen_keep_trying(url):
    for i in range(3):
        try:
            f = urllib2.urlopen(url)
        except urllib2.HTTPError, error:
            if error.code == 404:
                raise
            pass
        except urllib2.URLError:
            pass
        else:
            return f
        print url, "failed"
        sleep(2)
        print "trying again"

def get_ia(ia):
    # read MARC record of scanned book from archive.org
    # try the XML first because it has better character encoding
    # if there is a problem with the XML switch to the binary MARC
    xml_file = ia + "_marc.xml"
    loc = ia + "/" + xml_file
    if os.path.exists(xml_path + xml_file):
        f = open(xml_path + xml_file)
    else:
        f = urlopen_keep_trying(base + loc)
    if f:
        try:
            return loc, read_xml.read_edition(f)
        except read_xml.BadXML:
            pass
    url = base + ia + "/" + ia + "_meta.mrc"
    f = urlopen_keep_trying(url)
    if not f:
        return None, None
    data = f.read()
    length = data[0:5]
    loc = ia + "/" + ia + "_meta.mrc:0:" + length
    return ia, fast_parse.read_edition(data, accept_electronic = True)

def files(archive_id):
    url = base + archive_id + "/" + archive_id + "_files.xml"
    for i in range(5):
        try:
            tree = et.parse(urlopen_keep_trying(url))
            break
        except xml.parsers.expat.ExpatError:
            sleep(2)
    assert tree
    for i in tree.getroot():
        assert i.tag == 'file'
        name = i.attrib['name']
        if name.endswith('.mrc') or name.endswith('.marc') or name.endswith('.out') or name.endswith('.dat') or name.endswith('.records.utf8'):
            size = i.find('size')
            if size is not None:
                yield name, int(size.text)
            else:
                yield name, None

def get_data(loc):
    try:
        filename, p, l = loc.split(':')
    except ValueError:
        return None
    if not os.path.exists(rc['marc_path'] + filename):
        return None
    f = open(rc['marc_path'] + filename)
    f.seek(int(p))
    buf = f.read(int(l))
    f.close()
    return buf

def get_from_archive(locator):
    (file, offset, length) = locator.split (":")
    offset = int (offset)
    length = int (length)

    r0, r1 = offset, offset+length-1
    url = 'http://www.archive.org/download/%s'% file

    assert 0 < length < 100000

    ureq = urllib2.Request(url, None, {'Range':'bytes=%d-%d'% (r0, r1)},)
    return urlopen_keep_trying(ureq).read(100000)

def read_marc_file(part, f, pos=0):
    for data, int_length in fast_parse.read_file(f):
        loc = "%s:%d:%d" % (part, pos, int_length)
        pos += int_length
        yield (pos, loc, data)

def test_get_ia():
    ia = "poeticalworksoft00grayiala"
    expect = {
        'publisher': ['Printed by C. Whittingham for T. N. Longman and O. Rees [etc]'],
        'number_of_pages': 223,
        'full_title': 'The poetical works of Thomas Gray with some account of his life and writings ; the whole carefully revised and illustrated by notes ; to which are annexed, Poems addressed to, and in memory of Mr. Gray ; several of which were never before collected.',
        'publish_date': '1800',
        'publish_country': 'enk',
        'authors': [
            {'db_name': 'Gray, Thomas 1716-1771.', 'name': 'Gray, Thomas'}
        ],
        'oclc': ['5047966']
    }
    assert get_ia(ia) == expect

