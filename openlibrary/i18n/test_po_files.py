import os
import xml.etree.ElementTree as ET

import pytest
from babel.messages.pofile import read_po

from openlibrary.i18n import get_locales

root = os.path.dirname(__file__)


def trees_equal(el1: ET.Element, el2: ET.Element, error=True):
    """
    Check if the tree data is the same
    >>> trees_equal(ET.fromstring('<root />'), ET.fromstring('<root />'))
    True
    >>> trees_equal(ET.fromstring('<root x="3" />'),
    ...               ET.fromstring('<root x="7" />'))
    True
    >>> trees_equal(ET.fromstring('<root x="3" y="12" />'),
    ...               ET.fromstring('<root x="7" />'), error=False)
    False
    >>> trees_equal(ET.fromstring('<root><a /></root>'),
    ...               ET.fromstring('<root />'), error=False)
    False
    >>> trees_equal(ET.fromstring('<root><a /></root>'),
    ...               ET.fromstring('<root><a>Foo</a></root>'), error=False)
    True
    >>> trees_equal(ET.fromstring('<root><a href="" /></root>'),
    ...               ET.fromstring('<root><a>Foo</a></root>'), error=False)
    False
    """
    try:
        assert el1.tag == el2.tag
        assert set(el1.attrib.keys()) == set(el2.attrib.keys())
        assert len(el1) == len(el2)
        for c1, c2 in zip(el1, el2):
            trees_equal(c1, c2)
    except AssertionError as e:
        if error:
            raise e
        else:
            return False
    return True


def gen_po_file_keys():
    for locale in get_locales():
        po_path = os.path.join(root, locale, 'messages.po')

        catalog = read_po(open(po_path, 'rb'))
        for key in catalog:
            yield locale, key


def gen_po_msg_pairs():
    for locale, key in gen_po_file_keys():
        if not isinstance(key.id, str):
            msgids, msgstrs = (key.id, key.string)
        else:
            msgids, msgstrs = ([key.id], [key.string])

        for msgid, msgstr in zip(msgids, msgstrs):
            if msgstr == "":
                continue
            yield locale, msgid, msgstr


def gen_html_entries():
    for locale, msgid, msgstr in gen_po_msg_pairs():
        if '</' not in msgid:
            continue
        yield pytest.param(locale, msgid, msgstr, id=f'{locale}-{msgid}')


@pytest.mark.parametrize("locale,msgid,msgstr", gen_html_entries())
def test_html_format(locale: str, msgid: str, msgstr: str):
    # Need this to support &nbsp;, since ET only parses XML.
    # Find a better solution?
    entities = '<!DOCTYPE text [ <!ENTITY nbsp "&#160;"> ]>'
    id_tree = ET.fromstring(f'{entities}<root>{msgid}</root>')
    str_tree = ET.fromstring(f'{entities}<root>{msgstr}</root>')
    if not msgstr.startswith('<!-- i18n-lint no-tree-equal -->'):
        assert trees_equal(id_tree, str_tree)
