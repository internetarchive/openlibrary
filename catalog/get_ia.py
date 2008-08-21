import catalog.marc.fast_parse as fast_parse
import catalog.marc.read_xml as read_xml
from urllib2 import urlopen

base = "http://archive.org/download/"

def get_ia(ia):
    # read MARC record of scanned book from archive.org
    # try the XML first because it has better character encoding
    # if there is a problem with the XML switch to the binary MARC
    try:
        return read_xml.read_edition(ia)
    except read_xml.BadXML:
        pass
    url = base + ia + "/" + ia + "_meta.mrc"
    return fast_parse.read_edition(urlopen(url).read())

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

