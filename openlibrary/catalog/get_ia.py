import traceback
import xml.parsers.expat

from infogami import config
from lxml import etree
import requests
from time import sleep

from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.marc_xml import MarcXml
from openlibrary.core import ia


IA_BASE_URL = config.get('ia_base_url')
IA_DOWNLOAD_URL = f'{IA_BASE_URL}/download/'
MAX_MARC_LENGTH = 100000


def urlopen_keep_trying(url, headers=None, **kwargs):
    """Tries to request the url three times, raises HTTPError if 403, 404, or 416.  Returns a requests.Response"""
    for i in range(3):
        try:
            resp = requests.get(url, headers=headers, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as error:
            if error.response.status_code in (403, 404, 416):
                raise
        sleep(2)


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

    item_base = f'{IA_DOWNLOAD_URL}{identifier}/'

    # Try marc.xml first
    if marc_xml_filename in filenames:
        data = urlopen_keep_trying(item_base + marc_xml_filename).content
        try:
            root = etree.fromstring(data)
            return MarcXml(root)
        except Exception as e:
            print("Unable to read MarcXML: %s" % e)
            traceback.print_exc()

    # If that fails, try marc.bin
    if marc_bin_filename in filenames:
        data = urlopen_keep_trying(item_base + marc_bin_filename).content
        return MarcBinary(data)


def files(identifier):
    url = item_file_url(identifier, 'files.xml')
    for i in range(5):
        try:
            tree = etree.parse(urlopen_keep_trying(url).content)
            break
        except xml.parsers.expat.ExpatError:
            sleep(2)
    try:
        tree = etree.parse(urlopen_keep_trying(url).content)
    except:
        print("error reading", url)
        raise
    assert tree
    for i in tree.getroot():
        assert i.tag == 'file'
        name = i.attrib['name']
        if name == 'wfm_bk_marc' or name.endswith(
            ('.dat', '.marc', '.mrc', '.out', '.records.utf8')
        ):
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
    filename, offset, length = locator.split(":")
    offset = int(offset)
    length = int(length)

    r0, r1 = offset, offset + length - 1
    # get the next record's length in this request
    r1 += 5
    url = IA_DOWNLOAD_URL + filename

    assert 0 < length < MAX_MARC_LENGTH

    response = urlopen_keep_trying(url, headers={'Range': 'bytes=%d-%d' % (r0, r1)})
    data = None
    if response:
        # this truncates the data to MAX_MARC_LENGTH, but is probably not necessary here?
        data = response.content[:MAX_MARC_LENGTH]
        len_in_rec = int(data[:5])
        if len_in_rec != length:
            data, next_offset, next_length = get_from_archive_bulk(
                '%s:%d:%d' % (filename, offset, len_in_rec)
            )
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


def item_file_url(identifier, ending, host=None, path=None):
    if host and path:
        url = f'http://{host}{path}/{identifier}_{ending}'
    else:
        url = '{0}{1}/{1}_{2}'.format(IA_DOWNLOAD_URL, identifier, ending)
    return url


def marc_formats(identifier, host=None, path=None):
    files = {
        identifier + '_marc.xml': 'xml',
        identifier + '_meta.mrc': 'bin',
    }
    has = {'xml': False, 'bin': False}
    url = item_file_url(identifier, 'files.xml', host, path)
    for attempt in range(10):
        f = urlopen_keep_trying(url)
        if f is not None:
            break
        sleep(10)
    if f is None:
        # TODO: log this, if anything uses this code
        msg = "error reading %s_files.xml" % identifier
        return has
    data = f.content
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
