import os
import re
from itertools import groupby

import pytest
from babel.messages.pofile import read_po
import xml.etree.ElementTree as etree

from openlibrary.i18n import get_locales

root = os.path.dirname(__file__)
# Fix these and then remove them from this list
ALLOW_FAILURES = ('cs', 'hr', 'pl')


def parse_cfmt(string: str):
    """
    Extract e.g. '%s' from cstyle python format strings
    >>> parse_cfmt('hello %s')
    ['%s']
    >>> parse_cfmt(' by %(name)s')
    ['%(name)s']
    >>> parse_cfmt('%(count)d Lists')
    ['%(count)d']
    >>> parse_cfmt('100%% Complete!')
    ['%%']
    >>> parse_cfmt('%(name)s avez %(count)s listes.')
    ['%(name)s', '%(count)s']
    >>> parse_cfmt('')
    []
    >>> parse_cfmt('Hello World')
    []
    """
    cfmt_re = r'''
        (
            %(?:
                (?:\([a-zA-Z_][a-zA-Z0-9_]*?\))?   # e.g. %(blah)s
                (?:[-+0 #]{0,5})                   # optional flags
                (?:\d+|\*)?                        # width
                (?:\.(?:\d+|\*))?                  # precision
                (?:h|l|ll|w|I|I32|I64)?            # size
                [cCdiouxXeEfgGaAnpsSZ]             # type
            )
        )
        |                                # OR
        %%                               # literal "%%"
    '''

    return [
        m.group(0)
        for m in re.finditer(cfmt_re, string, flags=re.VERBOSE)
    ]


def cfmt_fingerprint(string: str):
    """
    Get a fingerprint dict of the cstyle format in this string
    >>> cfmt_fingerprint('hello %s')
    {'%s': 1}
    >>> cfmt_fingerprint('hello %s and %s')
    {'%s': 2}
    >>> cfmt_fingerprint('hello %(title)s. %(first)s %(last)s')
    {'%(title)s': 1, '%(first)s': 1, '%(last)s': 1}
    """
    pieces = parse_cfmt(string)
    return {
        key: len(list(grp))
        for key, grp in groupby(pieces)
    }


def trees_equal(el1: etree.Element, el2: etree.Element, error=True):
    """
    Check if the tree data is the same
    >>> trees_equal(etree.fromstring('<root />'), etree.fromstring('<root />'))
    True
    >>> trees_equal(etree.fromstring('<root x="3" />'),
    ...               etree.fromstring('<root x="7" />'))
    True
    >>> trees_equal(etree.fromstring('<root x="3" y="12" />'),
    ...               etree.fromstring('<root x="7" />'), error=False)
    False
    >>> trees_equal(etree.fromstring('<root><a /></root>'),
    ...               etree.fromstring('<root />'), error=False)
    False
    >>> trees_equal(etree.fromstring('<root><a /></root>'),
    ...               etree.fromstring('<root><a>Foo</a></root>'), error=False)
    True
    >>> trees_equal(etree.fromstring('<root><a href="" /></root>'),
    ...               etree.fromstring('<root><a>Foo</a></root>'), error=False)
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


def gen_python_format_entries():
    """Generate a tuple for every msgid/msgstr in our po files"""
    for locale, msgid, msgstr in gen_po_msg_pairs():
        if not ('%' in msgid or '%' in msgstr):
            continue

        if locale in ALLOW_FAILURES:
            yield pytest.param(locale, msgid, msgstr, id=f'{locale}-{msgid}',
                               marks=pytest.mark.xfail)
        else:
            yield pytest.param(locale, msgid, msgstr, id=f'{locale}-{msgid}')


def gen_html_entries():
    for locale, msgid, msgstr in gen_po_msg_pairs():
        if '</' not in msgid:
            continue

        if locale in ALLOW_FAILURES:
            yield pytest.param(locale, msgid, msgstr, id=f'{locale}-{msgid}',
                               marks=pytest.mark.xfail)
        else:
            yield pytest.param(locale, msgid, msgstr, id=f'{locale}-{msgid}')


@pytest.mark.parametrize("locale,msgid,msgstr", gen_python_format_entries())
def test_python_format(locale: str, msgid: str, msgstr: str):
    assert cfmt_fingerprint(msgid) == cfmt_fingerprint(msgstr)


@pytest.mark.parametrize("locale,msgid,msgstr", gen_html_entries())
def test_html_format(locale: str, msgid: str, msgstr: str):
    id_tree = etree.fromstring(f'<root>{msgid}</root>')
    str_tree = etree.fromstring(f'<root>{msgstr}</root>')
    assert trees_equal(id_tree, str_tree)
