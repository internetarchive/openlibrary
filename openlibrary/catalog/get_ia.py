from openlibrary.catalog.marc import fast_parse, read_xml, is_display_marc
from lxml import etree
import xml.parsers.expat
import urllib2, os.path, socket
from openlibrary.catalog.read_rc import read_rc
from time import sleep
from openlibrary.utils.ia import find_item

base = "http://archive.org/download/"

rc = read_rc()

class NoMARCXML:
    pass

def urlopen_keep_trying(url):
    for i in range(3):
        try:
            f = urllib2.urlopen(url)
        except urllib2.HTTPError, error:
            if error.code in (403, 404):
                #print "404 for '%s'" % url
                raise
            else:
                print 'error:', error.code, error.msg
            pass
        except urllib2.URLError:
            pass
        else:
            return f
        print url, "failed"
        sleep(2)
        print "trying again"

def bad_ia_xml(ia):
    if ia == 'revistadoinstit01paulgoog':
        return False
    # need to handle 404s:
    # http://www.archive.org/details/index1858mary
    loc = ia + "/" + ia + "_marc.xml"
    return '<!--' in urlopen_keep_trying(base + loc).read()

def get_marc_ia_data(ia):
    ia = ia.strip() # 'cyclopdiaofedu00kidd '
    url = base + ia + "/" + ia + "_meta.mrc"
    f = urlopen_keep_trying(url)
    if f is None:
        return None
    return f.read()

def get_marc_ia(ia):
    ia = ia.strip() # 'cyclopdiaofedu00kidd '
    url = base + ia + "/" + ia + "_meta.mrc"
    data = urlopen_keep_trying(url).read()
    length = int(data[0:5])
    if len(data) != length:
        data = data.decode('utf-8').encode('raw_unicode_escape')
    assert len(data) == length

    assert 'Internet Archive: Error' not in data
    print 'leader:', data[:24]
    return data
    return fast_parse.read_edition(data, accept_electronic = True)

def get_ia(ia):
    ia = ia.strip() # 'cyclopdiaofedu00kidd '
    # read MARC record of scanned book from archive.org
    # try the XML first because it has better character encoding
    # if there is a problem with the XML switch to the binary MARC
    xml_file = ia + "_marc.xml"
    loc = ia + "/" + xml_file
    try:
        print base + loc
        f = urlopen_keep_trying(base + loc)
    except urllib2.HTTPError, error:
        if error.code == 404:
            raise NoMARCXML
        else:
            print 'error:', error.code, error.msg
            raise
    assert f
    if f:
        try:
            return read_xml.read_edition(f)
        except read_xml.BadXML:
            pass
        except xml.parsers.expat.ExpatError:
            #print 'IA:', `ia`
            #print 'XML parse error:', base + loc
            pass
    print base + loc
    if '<title>Internet Archive: Page Not Found</title>' in urllib2.urlopen(base + loc).read(200):
        raise NoMARCXML
    url = base + ia + "/" + ia + "_meta.mrc"
    print url
    try:
        f = urlopen_keep_trying(url)
    except urllib2.URLError:
        pass
    if not f:
        return None
    data = f.read()
    length = data[0:5]
    loc = ia + "/" + ia + "_meta.mrc:0:" + length
    if len(data) == 0:
        print 'zero length MARC for', url
        return None
    if 'Internet Archive: Error' in data:
        print 'internet archive error for', url
        return None
    if data.startswith('<html>\n<head>'):
        print 'internet archive error for', url
        return None
    try:
        return fast_parse.read_edition(data, accept_electronic = True)
    except (ValueError, AssertionError, fast_parse.BadDictionary):
        print `data`
        raise

def files(archive_id):
    url = base + archive_id + "/" + archive_id + "_files.xml"
    for i in range(5):
        try:
            tree = etree.parse(urlopen_keep_trying(url))
            break
        except xml.parsers.expat.ExpatError:
            sleep(2)
    try:
        tree = etree.parse(urlopen_keep_trying(url))
    except:
        print "error reading", url
        raise
    assert tree
    for i in tree.getroot():
        assert i.tag == 'file'
        name = i.attrib['name']
        print 'name:', name
        if name == 'wfm_bk_marc' or name.endswith('.mrc') or name.endswith('.marc') or name.endswith('.out') or name.endswith('.dat') or name.endswith('.records.utf8'):
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
    marc_path = rc.get('marc_path')
    if not marc_path:
        return None
    if not os.path.exists(marc_path + '/' + filename):
        return None
    f = open(rc['marc_path'] + '/' + filename)
    f.seek(int(p))
    buf = f.read(int(l))
    f.close()
    return buf

def get_from_archive(locator):
    if locator.startswith('marc:'):
        locator = locator[5:]
    filename, offset, length = locator.split (":")
    offset = int (offset)
    length = int (length)

    ia, rest = filename.split('/', 1)

    for attempt in range(5):
        try:
            host, path = find_item(ia)
            break
        except socket.timeout:
            if attempt == 5:
                raise
            print 'retry, attempt', attempt

    r0, r1 = offset, offset+length-1
    url = 'http://' + host + path + '/' + rest 

    assert 0 < length < 100000

    ureq = urllib2.Request(url, None, {'Range':'bytes=%d-%d'% (r0, r1)},)

    f = None
    for i in range(3):
        try:
            f = urllib2.urlopen(ureq)
        except urllib2.HTTPError, error:
            if error.code == 416:
                raise
            elif error.code == 404:
                print "404 for '%s'" % url
                raise
            else:
                print url
                print 'error:', error.code, error.msg
        except urllib2.URLError:
            pass
    if f:
        return f.read(100000)
    else:
        print locator, url, 'failed'

def get_from_local(locator):
    try:
        file, offset, length = locator.split(':')
    except:
        print 'locator:', `locator`
        raise
    f = open(rc['marc_path'] + '/' + file)
    f.seek(int(offset))
    buf = f.read(int(length))
    f.close()
    return buf

def read_marc_file(part, f, pos=0):
    try:
        for data, int_length in fast_parse.read_file(f):
            loc = "marc:%s:%d:%d" % (part, pos, int_length)
            pos += int_length
            yield (pos, loc, data)
    except ValueError:
        print f
        raise

def marc_formats(ia, host=None, path=None):
    files = {
        ia + '_marc.xml': 'xml',
        ia + '_meta.mrc': 'bin',
    }
    has = { 'xml': False, 'bin': False }
    if host and path:
        url = 'http://%s%s/%s_files.xml' % (ia, host, path)
    else:
        url = 'http://www.archive.org/download/' + ia + '/' + ia + '_files.xml'
    for attempt in range(10):
        f = urlopen_keep_trying(url)
        if f is not None:
            break
        sleep(10)
    if f is None:
        msg_from = 'load_scribe@archive.org'
        msg_to = ['edward@archive.org']
        subject = "error reading %s_files.xml" % ia
        msg = url
        error_mail(msg_from, msg_to, subject, msg)
        return has
    data = f.read()
    try:
        root = etree.fromstring(data)
    except:
        print 'bad:', `data`
        return has
    for e in root:
        name = e.attrib['name']
        if name in files:
            has[files[name]] = True
        if all(has.values()):
            break
    return has

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

