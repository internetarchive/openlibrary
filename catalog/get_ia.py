import catalog.marc.fast_parse as fast_parse
import catalog.marc.read_xml as read_xml
import xml.etree.ElementTree as et
import xml.parsers.expat
import urllib2

base = "http://archive.org/download/"

def urlopen_keep_trying(url):
    while True:
        try:
            f = urllib2.urlopen(url)
        except urllib2.HTTPError, error:
            if error == 404:
                raise
            pass
        except urllib2.URLError:
            pass
        else:
            return f
        print url, "failed"
        sleep(5)
        print "trying again"

def get_ia(ia):
    # read MARC record of scanned book from archive.org
    # try the XML first because it has better character encoding
    # if there is a problem with the XML switch to the binary MARC
    try:
        loc = ia + "/" + ia + "_marc.xml"
        url = base + loc
        f = urlopen_keep_trying(url)
        return loc, read_xml.read_edition(f)
    except read_xml.BadXML:
        pass
    url = base + ia + "/" + ia + "_meta.mrc"
    f = urlopen_keep_trying(url)
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
        if name.endswith('.mrc') or name.endswith('.marc') or name.endswith('.out') or name.endswith('.dat'):
            yield archive_id + "/" + name

def get_from_archive(locator):
    (file, offset, length) = locator.split (":")
    offset = int (offset)
    length = int (length)

    r0, r1 = offset, offset+length-1
    url = 'http://www.archive.org/download/%s'% file

    assert 0 < length < 100000

    ureq = urllib2.Request(url, None, {'Range':'bytes=%d-%d'% (r0, r1)},)
    return urllib2.urlopen(ureq).read(100000)

def read_marc_file(part, f):
    pos = 0
    buf = None
    while 1:
        if buf:
            length = buf[:5]
            int_length = int(length)
        else:
            length = f.read(5)
            buf = length
        if length == "":
            break
        try:
            assert length.isdigit()
        except AssertionError:
            print `length`
            raise
        int_length = int(length)
        data = buf + f.read(int_length - len(buf))
        buf = None
        if data.find('\x1d') == -1:
            data += f.read(40)
            int_length = data.find('\x1d') + 1
            print `data[-40:]`
            assert int_length
            buf = data[int_length:]
            data = data[:int_length]
        assert data.endswith("\x1e\x1d")
        if len(data) < int_length:
            break
        loc = "%s:%d:%d" % (part, pos, int_length)
        pos += int_length
        yield (loc, data)

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

