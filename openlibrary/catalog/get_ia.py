from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.marc_xml import MarcXml
from openlibrary.catalog.marc import parse
from lxml import etree
import xml.parsers.expat
import urllib2, os.path, socket
from time import sleep
import traceback
from openlibrary.core import ia

base = "https://archive.org/download/"
MAX_MARC_LENGTH = 100000

class NoMARCXML(IOError):
    pass

def urlopen_keep_trying(url):
    for i in range(3):
        try:
            f = urllib2.urlopen(url)
            return f
        except urllib2.HTTPError, error:
            if error.code in (403, 404, 416):
                raise
        except urllib2.URLError:
            pass
        sleep(2)

def bad_ia_xml(ia):
    if ia == 'revistadoinstit01paulgoog':
        return False
    # need to handle 404s:
    # http://www.archive.org/details/index1858mary
    loc = ia + "/" + ia + "_marc.xml"
    return '<!--' in urlopen_keep_trying(base + loc).read()

def get_marc_ia_data(ia, host=None, path=None):
    """
    DEPRECATED
    """
    ending = 'meta.mrc'
    if host and path:
        url = 'http://%s%s/%s_%s' % (host, path, ia, ending)
    else:
        url = base + ia + '/' + ia + '_' + ending
    f = urlopen_keep_trying(url)
    return f.read() if f else None

def get_marc_record_from_ia(identifier):
    """
    Takes IA identifiers and returns MARC record instance.
    08/2018: currently called by openlibrary/plugins/importapi/code.py
    when the /api/import/ia endpoint is POSTed to.

    :param str identifier: ocaid
    :rtype: MarcXML | MarcBinary
    """
    metadata = ia.get_metadata(identifier)
    filenames = metadata['_filenames']

    marc_xml_filename = identifier + "_marc.xml"
    marc_bin_filename = identifier + "_meta.mrc"

    item_base = base + "/" + identifier + "/"

    # Try marc.xml first
    if marc_xml_filename in filenames:
        data = urlopen_keep_trying(item_base + marc_xml_filename).read()
        try:
            root = etree.fromstring(data)
            return MarcXml(root)
        except Exception as e:
            print "Unable to read MarcXML: %s" % e
            traceback.print_exc()

    # If that fails, try marc.bin
    if marc_bin_filename in filenames:
        data = urlopen_keep_trying(item_base + marc_bin_filename).read()
        return MarcBinary(data)

def get_ia(identifier):
    """
    DEPRECATED: Use get_marc_record_from_ia() above + parse.read_edition()

    :param str identifier: ocaid
    :rtype: dict
    """
    marc = get_marc_record_from_ia(identifier)
    return parse.read_edition(marc)

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
    """
    Gets a single binary MARC record from within an Archive.org
    bulk MARC item - data only.

    :param str locator: Locator ocaid/filename:offset:length
    :rtype: str|None
    :return: Binary MARC data
    """
    data, offset, length = get_from_archive_bulk(locator)
    return data

def get_from_archive_bulk(locator):
    """
    Gets a single binary MARC record from within an Archive.org
    bulk MARC item, and return the offset and length of the next
    item.
    If offset or length are `None`, then there is no next record.

    :param str locator: Locator ocaid/filename:offset:length
    :rtype: (str|None, int|None, int|None)
    :return: (Binary MARC data, Next record offset, Next record length)
    """
    if locator.startswith('marc:'):
        locator = locator[5:]
    filename, offset, length = locator.split (":")
    offset = int(offset)
    length = int(length)

    r0, r1 = offset, offset+length-1
    # get the next record's length in this request
    r1 += 5
    url = base + filename

    assert 0 < length < MAX_MARC_LENGTH

    ureq = urllib2.Request(url, None, {'Range': 'bytes=%d-%d' % (r0, r1)})
    f = urlopen_keep_trying(ureq)
    data = None
    if f:
        data = f.read(MAX_MARC_LENGTH)
        len_in_rec = int(data[:5])
        if len_in_rec != length:
            data, next_offset, next_length = get_from_archive_bulk('%s:%d:%d' % (filename, offset, len_in_rec))
        else:
            next_length = data[length:]
            data = data[:length]
            if len(next_length) == 5:
                # We have data for the next record
                next_offset = offset + len_in_rec
                next_length = int(next_length)
            else:
                next_offset = next_length = None
    return data, next_offset, next_length

def get_from_local(locator):
    try:
        file, offset, length = locator.split(':')
    except:
        print('locator:', repr(locator))
        raise
    f = open(rc['marc_path'] + '/' + file)
    f.seek(int(offset))
    buf = f.read(int(length))
    f.close()
    return buf

def read_marc_file(part, f, pos=0):
    """
    Generator to step through bulk MARC data f.

    :param str part:
    :param str f: Full binary MARC data containing many records
    :param int pos: Start position within the data
    :rtype: (int, str, str)
    :return: (Next position, Current source_record name, Current single MARC record)
    """
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
    ending = 'files.xml'
    if host and path:
        url = 'http://%s%s/%s_%s' % (host, path, ia, ending)
    else:
        url = base + ia + '/' + ia + '_' + ending
    for attempt in range(10):
        f = urlopen_keep_trying(url)
        if f is not None:
            break
        sleep(10)
    if f is None:
        #TODO: log this, if anything uses this code
        msg = "error reading %s_files.xml" % ia
        return has
    data = f.read()
    try:
        root = etree.fromstring(data)
    except:
        print('bad:', repr(data))
        return has
    for e in root:
        name = e.attrib['name']
        if name in files:
            has[files[name]] = True
        if all(has.values()):
            break
    return has
