from time import sleep

import lxml.etree
import requests
from lxml import etree

from infogami import config
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.marc_xml import MarcXml
from openlibrary.core import ia

IA_BASE_URL = config.get('ia_base_url')
IA_DOWNLOAD_URL = f'{IA_BASE_URL}/download/'
MAX_MARC_LENGTH = 100000


def urlopen_keep_trying(url: str, headers=None, **kwargs):
    """Tries to request the url three times, raises HTTPError if 403, 404, or 416.  Returns a requests.Response"""
    for i in range(3):
        try:
            resp = requests.get(url, headers=headers, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as error:
            if error.response and error.response.status_code in (403, 404, 416):
                raise
        sleep(2)


def get_marc_record_from_ia(
    identifier: str, ia_metadata: dict | None = None
) -> MarcBinary | MarcXml | None:
    """
    Takes IA identifiers and optional IA metadata and returns MARC record instance.
    08/2018: currently called by openlibrary/plugins/importapi/code.py
    when the /api/import/ia endpoint is POSTed to.

    :param ia_metadata: The full ia metadata; e.g. https://archive.org/metadata/goody,
                        not https://archive.org/metadata/goody/metadata
    """
    if ia_metadata is None:
        ia_metadata = ia.get_metadata(identifier)
    filenames = ia_metadata['_filenames']  # type: ignore[index]

    marc_xml_filename = identifier + '_marc.xml'
    marc_bin_filename = identifier + '_meta.mrc'

    item_base = f'{IA_DOWNLOAD_URL}{identifier}/'

    # Try marc.bin first
    if marc_bin_filename in filenames:
        data = urlopen_keep_trying(item_base + marc_bin_filename).content
        return MarcBinary(data)

    # If that fails, try marc.xml
    if marc_xml_filename in filenames:
        data = urlopen_keep_trying(item_base + marc_xml_filename).content
        root = etree.fromstring(
            data, parser=lxml.etree.XMLParser(resolve_entities=False)
        )
        return MarcXml(root)
    return None


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
