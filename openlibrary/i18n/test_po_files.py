import os
import xml.etree.ElementTree as ET
from io import BytesIO

import pytest
from babel.messages.catalog import Catalog, Message
from babel.messages.pofile import read_po

from openlibrary import i18n
from openlibrary.i18n import get_locales
from openlibrary.i18n.validators import _form0_may_carry_plural_placeholders, validate

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


def _read_catalog(locale: str) -> Catalog:
    po_path = os.path.join(root, locale, "messages.po")
    with open(po_path, "rb") as fil:
        return read_po(fil)


def test_html_format():
    errors: list[str] = []
    for locale in get_locales():
        catalog = _read_catalog(locale)
        for message in catalog:
            # Same expansion gen_po_msg_pairs() did: plural messages carry a
            # tuple of msgids/msgstrs; untranslated (empty) msgstrs are skipped.
            if not isinstance(message.id, str):
                msgids, msgstrs = (message.id, message.string)
            else:
                msgids, msgstrs = ([message.id], [message.string])

            for msgid, msgstr in zip(msgids, msgstrs):
                if msgstr == "" or "</" not in msgid:
                    continue
                if msgstr.startswith("<!-- i18n-lint no-tree-equal -->"):
                    continue
                # Need this to support &nbsp;, since ET only parses XML.
                # Find a better solution?
                entities = '<!DOCTYPE text [ <!ENTITY nbsp "&#160;"> ]>'
                id_tree = ET.fromstring(f"{entities}<root>{msgid}</root>")
                str_tree = ET.fromstring(f"{entities}<root>{msgstr}</root>")
                # For translations that correctly reorder elements to fit the target language's word order
                ordered = not msgstr.startswith("<!-- i18n-lint no-tree-order -->")
                try:
                    assert trees_equal(id_tree, str_tree, ordered=ordered)
                except AssertionError:
                    errors.append(f"{locale}:{message.lineno}:\nmsgid:  {msgid}\nmsgstr: {msgstr}")
    assert errors == []


def test_validate():
    errors: list[str] = []
    for locale in get_locales():
        catalog = _read_catalog(locale)
        for message in catalog:
            # The same selection as `make test-i18n`, so the two cannot disagree
            if message.lineno and (errs := validate(message, catalog)):
                errors.extend(f"{locale}:{message.lineno}: {err}" for err in errs)
    assert errors == []


@pytest.mark.parametrize(
    ("msgstr", "has_errors"),
    [('<a href="%s">ti</a>', False), ('<a href="%(link)s">ti</a>', True)],
)
def test_validate_translations_counts_non_fuzzy_errors(tmp_path, monkeypatch, msgstr, has_errors):
    (tmp_path / "xx").mkdir()
    (tmp_path / "xx" / "messages.po").write_text(
        f'msgid ""\nmsgstr ""\n\n#, python-format\nmsgid "by <a href=\\"%s\\">You</a>"\nmsgstr "{msgstr.replace('"', '\\"')}"\n'
    )
    monkeypatch.setattr(i18n, "root", str(tmp_path))
    assert (i18n.validate_translations(["xx"])["xx"] > 0) == has_errors


@pytest.mark.parametrize(
    ("msgid", "msgstr", "valid"),
    [
        # Named placeholders are looked up by key, so a translation may reorder or repeat them
        ("%(username)s has read %(total)d books. Join %(username)s", "%(total)d книг прочитані %(username)s. Приєднайтеся до %(username)s", True),
        ("%(username)s is reading %(total)d books. Join %(username)s", "%(username)s이(가) %(total)d권을 읽고", True),
        # Positional ones are consumed in order
        ("%s has %d books", "%d books by %s", False),
        # Same-type positional swaps render in the wrong order without raising
        ("%d of %i", "%i od %d", False),
        ('by <a href="%s">You</a>', '<a href="%(link)s">ti</a>', False),
        ("%(count)s commits behind", "%(count)개 커밋 뒤처짐", False),
        # A `%d` translation raises on the str a `%s` msgid accepts
        ("%(n)s waiting", "%(n)d waiting", False),
        (("%(count)d item", "%(count)d items"), ("%(count)d개 항목",), True),
        # Babel's checker reads a malformed conversion as "no placeholders", in every plural form
        (("%(count)d item", "%(count)d items"), ("%(count)개 항목",), False),
        (("%(count)d item", "%(count)d items"), ("%(count)d stavka", "%(count)d stavke", "%(count)đ stavki"), False),
        # `%c` accepts a 1-character str, so the probe value must be longer than that
        (("One item", "%(count)s items"), ("%(count)c개",), False),
        # A mapping fills a positional `%s` with its own repr instead of raising
        (("One item", "%(count)d items"), ("%s개 항목",), False),
    ],
)
def test_validate_placeholders(msgid, msgstr, valid):
    catalog = Catalog(locale="ko" if len(msgstr) == 1 else "hr")
    catalog.add(msgid, msgstr, flags=["python-format"])
    assert (validate(catalog[msgid if isinstance(msgid, str) else msgid[0]], catalog) == []) == valid


PLURAL_RULES = {
    "nplurals=1": "nplurals=1; plural=0;",
    "de": "nplurals=2; plural=(n != 1);",
    "fr": "nplurals=2; plural=(n > 1);",
    "ru": "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : 2);",
    "pl": "nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);",
}


def _plural_errors(rule: str, msgid: tuple[str, str], msgstrs: tuple[str, ...]) -> list[str]:
    def q(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    po = f'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Plural-Forms: {rule}\\n"\n\n'
    po += f'#, python-format\nmsgid "{q(msgid[0])}"\nmsgid_plural "{q(msgid[1])}"\n'
    po += "".join(f'msgstr[{i}] "{q(s)}"\n' for i, s in enumerate(msgstrs))
    catalog = read_po(BytesIO(po.encode()))
    return validate(catalog[msgid], catalog)


LISTS = ("%(name)s has 1 list.", "%(name)s has %(count)s lists.")
MERGED = ("%(who)s merged one duplicate of %(master)s", "%(who)s merged %(count)d duplicates of %(master)s")
MERGED_ANON = ("one duplicate of %(master)s was merged anonymously", "%(count)d duplicates of %(master)s were merged anonymously")


@pytest.mark.parametrize(
    ("lang", "msgid", "msgstrs"),
    [
        # The 12 entries openlibrary-i18n@3dc9295 ships that `make test-i18n` rejected, verbatim
        ("ja", LISTS, ("%(name)sには%(count)s件のリストがあります。",)),
        ("ja", MERGED, ("%(who)sが%(master)sの重複%(count)d件を統合しました",)),
        ("ja", MERGED_ANON, ("%(master)sの重複%(count)d件が匿名で統合されました",)),
        ("id", LISTS, ("%(name)s memiliki %(count)s daftar.",)),
        ("id", MERGED, ("%(who)s menggabungkan %(count)d duplikat dari %(master)s",)),
        ("id", MERGED_ANON, ("%(count)d duplikat dari %(master)s digabungkan secara anonim",)),
        ("ko", LISTS, ("%(name)s님의 목록이 %(count)s개 있습니다.",)),
        ("ko", MERGED, ("%(who)s님이 %(master)s의 중복 항목 %(count)d개를 병합했습니다.",)),
        ("ko", MERGED_ANON, ("%(master)s의 중복 항목 %(count)d개가 익명으로 병합되었습니다.",)),
        ("ru", LISTS, ("У %(name)s есть %(count)s список.", "У %(name)s есть %(count)s списка.", "У %(name)s есть %(count)s списков.")),  # noqa: RUF001
        (
            "ru",
            MERGED,
            (
                "%(who)s объединил %(count)d дубликат %(master)s",
                "%(who)s объединил %(count)d дубликата %(master)s",
                "%(who)s объединил %(count)d дубликатов %(master)s",
            ),
        ),
        (
            "ru",
            MERGED_ANON,
            (
                "%(count)d дубликат %(master)s был объединён анонимно",
                "%(count)d дубликата %(master)s были объединены анонимно",
                "%(count)d дубликатов %(master)s было объединено анонимно",
            ),
        ),
    ],
)
def test_validate_accepts_count_in_plural_form_shown_beyond_one(lang, msgid, msgstrs):
    # In these languages msgstr[0] is also shown for n other than 1 (every n with
    # nplurals=1, n=21, 31, ... in ru), so it stands in for msgid_plural and must carry
    # the count. Babel's check compares it only with the singular msgid.
    rule = PLURAL_RULES["ru" if lang == "ru" else "nplurals=1"]
    assert _plural_errors(rule, msgid, msgstrs) == []


RU_REST = ("У %(name)s %(count)s списка.", "У %(name)s %(count)s списков.")  # noqa: RUF001


@pytest.mark.parametrize(
    ("rule", "msgid", "msgstrs"),
    [
        # Form 0 shown only at n=1: still checked against the singular msgid
        pytest.param("de", LISTS, ("%(name)s hat %(count)s Liste.", "%(name)s hat %(count)s Listen."), id="form0-only-at-one-2-forms"),
        pytest.param(
            "pl", LISTS, ("%(name)s ma %(count)s listę.", "%(name)s ma %(count)s listy.", "%(name)s ma %(count)s list."), id="form0-only-at-one-3-forms"
        ),
        # The singular's own placeholders are still required in form 0
        pytest.param("nplurals=1", ("%(who)s merged one duplicate", "%(who)s merged %(count)d duplicates"), ("%(count)d件",), id="drops-singular-name"),
        pytest.param("nplurals=1", ("one %s", "%(count)d of them"), ("それら",), id="mixed-kind-msgids"),
        # %r and %F are placeholders too (Babel's PYTHON_FORMAT), so these msgids also mix kinds
        pytest.param("nplurals=1", ("one %r", "%(count)d of them"), ("%(count)d件",), id="mixed-kind-msgids-r"),
        pytest.param("nplurals=1", ("one %F", "%(count)d of them"), ("%(count)d件",), id="mixed-kind-msgids-F"),
        # msgid_plural brings nothing the singular lacks, so Babel's singular check stands;
        # this renders, so only that guard (not the substitution check) rejects it
        pytest.param("nplurals=1", ("%(count)d list", "Lists"), ("%(count)s件",), id="plural-brings-nothing"),
        # Plural-Forms gettext cannot evaluate: the old singular-only check, no crash
        pytest.param("nplurals=2; plural=n ! = 1;", LISTS, ("%(name)s hat %(count)s Liste.", "%(name)s hat %(count)s Listen."), id="malformed-rule"),
        pytest.param("nplurals=2; plural=(1/n);", LISTS, ("%(name)s hat %(count)s Liste.", "%(name)s hat %(count)s Listen."), id="rule-divides-by-zero"),
    ],
)
def test_validate_still_rejects_plural_form0_mismatches(rule, msgid, msgstrs):
    assert _plural_errors(PLURAL_RULES.get(rule, rule), msgid, msgstrs) != []


@pytest.mark.parametrize(
    ("rule", "msgid", "msgstrs"),
    [
        pytest.param("nplurals=1", LISTS, ("%(name)sには%(wrong)s件のリストがあります。",), id="unknown-name-single-form"),
        pytest.param("ru", LISTS, ("У %(name)s %(wrong)s список.", *RU_REST), id="unknown-name-form-shown-at-21"),  # noqa: RUF001
        pytest.param("nplurals=1", LISTS, ("%(name)sには%(count)d件のリストがあります。",), id="type-mismatch-single-form"),
        pytest.param("nplurals=1", ("%(name)s has one list", "Many lists"), ("%(bogus)s",), id="plural-brings-nothing-unknown"),
        pytest.param("nplurals=1", ("%(name)s has one list", "Lists"), ("%(name)d件",), id="plural-brings-nothing-type"),
        pytest.param("fr", ("%(name)s has one list", "Lists"), ("%(name)s a %(count)d liste", "Des listes"), id="neither-msgid-has-name"),
        pytest.param("nplurals=1", ("%s of %d", "%s"), ("%s",), id="plural-fewer-positionals"),
    ],
)
def test_validate_rejects_plural_form0_that_would_raise(rule, msgid, msgstrs):
    # These raise when rendered, so #13780's substitution check rejects them whatever
    # the plural rule does; they pin that this change does not forgive them.
    assert _plural_errors(PLURAL_RULES.get(rule, rule), msgid, msgstrs) != []


def test_validate_rejects_type_change_only_babel_sees():
    # Renders fine with an int count, so only Babel's re-check against msgid_plural
    # (where the count is %d) rejects it.
    assert _plural_errors(PLURAL_RULES["nplurals=1"], ("%(name)s has 1 list", "%(name)s has %(count)d lists"), ("%(name)sには%(count)s件",)) != []


@pytest.mark.parametrize(
    ("msgid", "form0", "allowed"),
    [
        (LISTS, "%(name)sには%(count)s件", True),
        # msgid_plural brings nothing the singular lacks
        (("%(name)s has %(count)s list", "%(name)s has %(count)s lists"), "%(name)s %(count)s", False),
        (("%s of %d", "%s"), "%s", False),
        # form 0 must keep every singular placeholder
        (("%(who)s merged one", "%(who)s merged %(count)d"), "%(count)d件", False),
        # and use none outside the two msgids
        (LISTS, "%(name)s %(count)s %(extra)s", False),
        # positional count must match one of the msgids
        (("one item", "%d items"), "%d %d", False),
        # validate() never asks this (Babel's check skips a placeholder-free singular),
        # and only a msgid whose English singular already raises has this shape; kept to
        # mirror openlibrary-i18n's rule
        (("one item", "%d items"), "%d", True),
        # mixed positional/named msgids get no allowance
        (("one %s", "%(count)d of them"), "%(count)d", False),
    ],
)
def test_form0_may_carry_plural_placeholders(msgid, form0, allowed):
    assert _form0_may_carry_plural_placeholders(Message(msgid, (form0,))) == allowed
