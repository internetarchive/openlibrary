from __future__ import print_function
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.marc_xml import MarcXml
from openlibrary.catalog.marc import fast_parse, parse
from infogami import config
from lxml import etree
import xml.parsers.expat
import os.path
import socket
from time import sleep
import traceback
from openlibrary.core import ia

from six.moves import urllib


IA_BASE_URL = config.get('ia_base_url')
IA_DOWNLOAD_URL = '%s/download/' % IA_BASE_URL
MAX_MARC_LENGTH = 100000

class NoMARCXML(IOError):
    # DEPRECATED, rely on MarcXml to raise exceptions
    pass

def urlopen_keep_trying(url):
    for i in range(3):
        try:
            f = urllib.request.urlopen(url)
            return f
        except urllib.error.HTTPError as error:
            if error.code in (403, 404, 416):
                raise
        except urllib.error.URLError:
            pass
        sleep(2)

def bad_ia_xml(identifier):
    # DEPRECATED
    if identifier == 'revistadoinstit01paulgoog':
        return False
    # need to handle 404s:
    # http://www.archive.org/details/index1858mary
    loc = "{0}/{0}_marc.xml".format(identifier)
    return '<!--' in urlopen_keep_trying(IA_DOWNLOAD_URL + loc).read()

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

    marc_xml_filename = identifier + '_marc.xml'
    marc_bin_filename = identifier + '_meta.mrc'

    item_base = '{}{}/'.format(IA_DOWNLOAD_URL, identifier)

    # Try marc.xml first
    if marc_xml_filename in filenames:
        data = urlopen_keep_trying(item_base + marc_xml_filename).read()
        try:
            root = etree.fromstring(data)
            return MarcXml(root)
        except Exception as e:
            print("Unable to read MarcXML: %s" % e)
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

def files(identifier):
    url = item_file_url(identifier, 'files.xml')
    for i in range(5):
        try:
            tree = etree.parse(urlopen_keep_trying(url))
            break
        except xml.parsers.expat.ExpatError:
            sleep(2)
    try:
        tree = etree.parse(urlopen_keep_trying(url))
    except:
        print("error reading", url)
        raise
    assert tree
    for i in tree.getroot():
        assert i.tag == 'file'
        name = i.attrib['name']
        if name == 'wfm_bk_marc' or name.endswith('.mrc') or name.endswith('.marc') or name.endswith('.out') or name.endswith('.dat') or name.endswith('.records.utf8'):
            size = i.find('size')
            if size is not None:
                yield name, int(size.text)
            else:
                yield name, None

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
    url = IA_DOWNLOAD_URL + filename

    assert 0 < length < MAX_MARC_LENGTH

    ureq = urllib.request.Request(url, None, {'Range': 'bytes=%d-%d' % (r0, r1)})
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

def read_marc_file(part, f, pos=0):
    """
    Generator to step through bulk MARC data f.

    :param str part:
    :param str f: Full binary MARC data containing many records
    :param int pos: Start position within the data
    :rtype: (int, str, str)
    :return: (Next position, Current source_record name, Current single MARC record)
    """
    for data, int_length in fast_parse.read_file(f):
        loc = "marc:%s:%d:%d" % (part, pos, int_length)
        pos += int_length
        yield (pos, loc, data)

def item_file_url(identifier, ending, host=None, path=None):
    if host and path:
        url = 'http://{}{}/{}_{}'.format(host, path, identifier, ending)
    else:
        url = '{0}{1}/{1}_{2}'.format(IA_DOWNLOAD_URL, identifier, ending)
    return url

def get_marc_ia_data(identifier, host=None, path=None):
    """
    DEPRECATED
    """
    url = item_file_url(identifier, 'meta.mrc', host, path)
    f = urlopen_keep_trying(url)
    return f.read() if f else None

def marc_formats(identifier, host=None, path=None):
    files = {
        identifier + '_marc.xml': 'xml',
        identifier + '_meta.mrc': 'bin',
    }
    has = { 'xml': False, 'bin': False }
    url = item_file_url(identifier, 'files.xml', host, path)
    for attempt in range(10):
        f = urlopen_keep_trying(url)
        if f is not None:
            break
        sleep(10)
    if f is None:
        #TODO: log this, if anything uses this code
        msg = "error reading %s_files.xml" % identifier
        return has
    data = f.read()
    try:
        root = etree.fromstring(data)
    except:
        print(('bad:', repr(data)))
        return has
    for e in root:
        name = e.attrib['name']
        if name in files:
            has[files[name]] = True
        if all(has.values()):
            break
    return has

def get_from_local(locator):
    # DEPRECATED, Broken, undefined rc, will raise exception if called
    try:
        file, offset, length = locator.split(':')
    except:
        print(('locator:', repr(locator)))
        raise
    f = open(rc['marc_path'] + '/' + file)  # noqa: F821 DEPRECATED
    f.seek(int(offset))
    buf = f.read(int(length))
    f.close()
    return buf

def get_data(loc):
    # DEPRECATED, Broken, undefined rc, will return None or raise exception if called
    try:
        filename, p, l = loc.split(':')
    except ValueError:
        return None
    marc_path = rc.get('marc_path')
    if not marc_path:
        return None
    if not os.path.exists(marc_path + '/' + filename):
        return None
    f = open(rc['marc_path'] + '/' + filename)  # noqa: F821 DEPRECATED
    f.seek(int(p))
    buf = f.read(int(l))
    f.close()
    return buf
