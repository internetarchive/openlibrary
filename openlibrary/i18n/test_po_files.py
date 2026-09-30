import os
import xml.etree.ElementTree as ET

import pytest
from babel.messages.catalog import Catalog, Message
from babel.messages.pofile import read_po

from openlibrary import i18n
from openlibrary.i18n import get_locales
from openlibrary.i18n.validators import validate

root = os.path.dirname(__file__)


def trees_equal(el1: ET.Element, el2: ET.Element, error=True, ordered=True):
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
    >>> trees_equal(ET.fromstring('<root><a /><b /></root>'),
    ...               ET.fromstring('<root><b /><a /></root>'), error=False)
    False
    >>> trees_equal(ET.fromstring('<root><a /><b /></root>'),
    ...               ET.fromstring('<root><b /><a /></root>'), ordered=False)
    True
    >>> trees_equal(ET.fromstring('<root><a /><b /></root>'),
    ...               ET.fromstring('<root><b /><b /></root>'), error=False, ordered=False)
    False
    """
    try:
        assert el1.tag == el2.tag
        assert set(el1.attrib.keys()) == set(el2.attrib.keys())
        assert len(el1) == len(el2)
        if ordered:
            for c1, c2 in zip(el1, el2):
                trees_equal(c1, c2)
        else:
            unmatched = list(el2)
            for c1 in el1:
                match = next((c2 for c2 in unmatched if trees_equal(c1, c2, error=False, ordered=False)), None)
                assert match is not None, f"No match for <{c1.tag}> in translation"
                unmatched.remove(match)
    except AssertionError as e:
        if error:
            raise e
        else:
            return False
    return True


def gen_po_file_keys():
    for locale in get_locales():
        po_path = os.path.join(root, locale, "messages.po")

        with open(po_path, "rb") as fil:
            catalog = read_po(fil)
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
        if "</" not in msgid:
            continue
        yield pytest.param(locale, msgid, msgstr, id=f"{locale}-{msgid}")


@pytest.mark.parametrize(("locale", "msgid", "msgstr"), gen_html_entries())
def test_html_format(locale: str, msgid: str, msgstr: str):
    # Need this to support &nbsp;, since ET only parses XML.
    # Find a better solution?
    entities = '<!DOCTYPE text [ <!ENTITY nbsp "&#160;"> ]>'
    id_tree = ET.fromstring(f"{entities}<root>{msgid}</root>")
    str_tree = ET.fromstring(f"{entities}<root>{msgstr}</root>")
    if msgstr.startswith("<!-- i18n-lint no-tree-equal -->"):
        return
    # For translations that correctly reorder elements to fit the target language's word order
    ordered = not msgstr.startswith("<!-- i18n-lint no-tree-order -->")
    assert trees_equal(id_tree, str_tree, ordered=ordered)


def gen_po_messages():
    for locale in get_locales():
        with open(os.path.join(root, locale, "messages.po"), "rb") as fil:
            catalog = read_po(fil)
        for message in catalog:
            # The same selection as `make test-i18n`, so the two cannot disagree
            if message.lineno:
                yield pytest.param(message, catalog, id=f"{locale}:{message.lineno}")


@pytest.mark.parametrize(("message", "catalog"), gen_po_messages())
def test_validate(message: Message, catalog: Catalog):
    assert validate(message, catalog) == []


@pytest.mark.parametrize(
    ("msgstr", "expected_errors"),
    [('<a href="%s">ti</a>', 0), ('<a href="%(link)s">ti</a>', 3)],
)
def test_validate_translations_counts_non_fuzzy_errors(tmp_path, monkeypatch, msgstr, expected_errors):
    (tmp_path / "xx").mkdir()
    (tmp_path / "xx" / "messages.po").write_text(
        f'msgid ""\nmsgstr ""\n\n#, python-format\nmsgid "by <a href=\\"%s\\">You</a>"\nmsgstr "{msgstr.replace('"', '\\"')}"\n'
    )
    monkeypatch.setattr(i18n, "root", str(tmp_path))
    assert i18n.validate_translations(["xx"]) == {"xx": expected_errors}


@pytest.mark.parametrize(
    ("msgid", "msgstr", "valid"),
    [
        # Named placeholders are looked up by key, so a translation may reorder or repeat them
        ("%(username)s has read %(total)d books. Join %(username)s", "%(total)d книг прочитані %(username)s. Приєднайтеся до %(username)s", True),
        ("%(username)s is reading %(total)d books. Join %(username)s", "%(username)s이(가) %(total)d권을 읽고", True),
        # Positional ones are consumed in order
        ("%s has %d books", "%d books by %s", False),
        ('by <a href="%s">You</a>', '<a href="%(link)s">ti</a>', False),
        ("%(count)s commits behind", "%(count)개 커밋 뒤처짐", False),
        # A `%d` translation raises on the str a `%s` msgid accepts
        ("%(n)s waiting", "%(n)d waiting", False),
        (("%(count)d item", "%(count)d items"), ("%(count)d개 항목",), True),
        # Babel's checker reads a malformed conversion as "no placeholders", in every plural form
        (("%(count)d item", "%(count)d items"), ("%(count)개 항목",), False),
        (("%(count)d item", "%(count)d items"), ("%(count)d stavka", "%(count)d stavke", "%(count)đ stavki"), False),
    ],
)
def test_validate_placeholders(msgid, msgstr, valid):
    catalog = Catalog(locale="ko" if len(msgstr) == 1 else "hr")
    catalog.add(msgid, msgstr, flags=["python-format"])
    assert (validate(catalog[msgid if isinstance(msgid, str) else msgid[0]], catalog) == []) == valid
