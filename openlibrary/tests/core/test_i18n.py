from io import BytesIO

import pytest
import web
from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po, write_po
from babel.support import Translations

# The i18n module should be moved to core.
from openlibrary import i18n
from openlibrary.mocks.mock_infobase import MockSite


class MockTranslations(dict):
    def gettext(self, message):
        return self.get(message, message)

    def ungettext(self, message1, message2, n):
        if n == 1:
            return self.gettext(message1)
        else:
            return self.gettext(message2)


class MockLoadTranslations(dict):
    def __call__(self, lang):
        return self.get(lang)

    def init(self, lang, translations):
        self[lang] = MockTranslations(translations)


class Test_ungettext:
    @pytest.fixture(autouse=True)
    def setup_context(self, request_context_fixture):
        """Auto-use fixture to set up request context for all tests."""
        pass

    def setup_monkeypatch(self, monkeypatch):
        self.d = MockLoadTranslations()
        ctx = web.storage()

        monkeypatch.setattr(i18n, "load_translations", self.d)
        monkeypatch.setattr(web, "ctx", ctx)
        monkeypatch.setattr(web.webapi, "ctx", web.ctx)

        self._load_fake_context()
        web.ctx.lang = "en"
        web.ctx.site = MockSite()

    def _load_fake_context(self):
        self.app = web.application()
        self.env = {
            "PATH_INFO": "/",
            "HTTP_METHOD": "GET",
        }
        self.app.load(self.env)

    def test_ungettext(self, monkeypatch, request_context_fixture):
        self.setup_monkeypatch(monkeypatch)

        assert i18n.ungettext("book", "books", 1) == "book"
        assert i18n.ungettext("book", "books", 2) == "books"

        request_context_fixture(lang="fr")
        self.d.init(
            "fr",
            {
                "book": "libre",
                "books": "libres",
            },
        )

        assert i18n.ungettext("book", "books", 1) == "libre"
        assert i18n.ungettext("book", "books", 2) == "libres"

        request_context_fixture(lang="te")
        assert i18n.ungettext("book", "books", 1) == "book"
        assert i18n.ungettext("book", "books", 2) == "books"

    def test_ungettext_with_args(self, monkeypatch, request_context_fixture):
        self.setup_monkeypatch(monkeypatch)

        assert i18n.ungettext("one book", "%(n)d books", 1, n=1) == "one book"
        assert i18n.ungettext("one book", "%(n)d books", 2, n=2) == "2 books"

        request_context_fixture(lang="fr")
        self.d.init(
            "fr",
            {
                "one book": "un libre",
                "%(n)d books": "%(n)d libres",
            },
        )

        assert i18n.ungettext("one book", "%(n)d books", 1, n=1) == "un libre"
        assert i18n.ungettext("one book", "%(n)d books", 2, n=2) == "2 libres"


class Test_load_translations:
    @pytest.fixture(autouse=True)
    def isolated_translations(self, tmp_path, monkeypatch):
        monkeypatch.setattr(i18n, "root", str(tmp_path))
        i18n.load_translations.cache_clear()
        yield
        i18n.load_translations.cache_clear()

    def test_missing_locales_do_not_grow_cache_without_limit(self):
        for index in range(1024):
            assert i18n.load_translations(f"unsupported-{index}") is None

        assert i18n.load_translations.cache_info().currsize <= 256


class Test_pot_width:
    """``messages.pot`` is written with ``width=POT_WIDTH`` so Babel never wraps the
    ``#:`` location comments onto multiple lines, which is what caused spurious merge
    conflicts (#12837). These guard that behaviour against a future Babel change.
    """

    def _write_pot(self, catalog):
        buf = BytesIO()
        write_po(buf, catalog, include_lineno=False, width=i18n.POT_WIDTH)
        return buf.getvalue().decode("utf-8")

    def test_locations_stay_on_a_single_line(self):
        catalog = Catalog()
        # A string used in many files: at Babel's default width=76 this location list
        # would wrap across several #: lines; with POT_WIDTH it must stay on one.
        locations = [(f"some/template/with_a_longish_path_{n}.html", n) for n in range(12)]
        catalog.add("Reused string", locations=locations)
        pot = self._write_pot(catalog)

        location_lines = [line for line in pot.splitlines() if line.startswith("#:")]
        assert len(location_lines) == 1
        for filename, _ in locations:
            assert filename in location_lines[0]

    def test_flags_and_message_text_survive(self):
        catalog = Catalog()
        # python-format flag + a long string: confirm nothing but #: wrapping changes
        # (the "could fuzzy/other comments break?" concern -- they don't go through any
        # custom transform, Babel writes them as usual).
        catalog.add(
            "Created %(reference)s to track this error and we will investigate as we're able.",
            locations=[("internalerror.html", 1)],
            flags=["python-format"],
        )
        pot = self._write_pot(catalog)

        assert "#, python-format" in pot
        assert "Created %(reference)s" in pot


PO_HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n\n'


def _write_locale(base, lang, body):
    path = base / lang
    path.mkdir(parents=True, exist_ok=True)
    (path / "messages.po").write_text(PO_HEADER + body, encoding="utf-8")
    return path / "messages.po"


class Test_install_translations:
    """``install_translations`` is the gate olbase runs on ``.po`` files pulled from
    openlibrary-i18n. A file that would crash at render time or break ``make i18n``
    must not replace the committed one.
    """

    GOOD = 'msgid "by %(name)s"\nmsgstr "von %(name)s"\n'

    def test_installs_a_valid_file_into_a_new_language_directory(self, tmp_path):
        src, dest = tmp_path / "src", tmp_path / "dest"
        _write_locale(src, "xx", self.GOOD)
        dest.mkdir()

        assert i18n.install_translations(str(src), str(dest)) == {"xx": []}
        assert (dest / "xx" / "messages.po").read_text(encoding="utf-8").endswith(self.GOOD)

    @pytest.mark.parametrize(
        "body",
        [
            # hr:5752 on openlibrary master: positional msgid, named msgstr -> TypeError
            pytest.param('msgid "by <a href=\\"%s\\">You</a>"\nmsgstr "od <a href=\\"%(link)s\\">ti</a>"\n', id="positional-to-named"),
            # ko:1181 on openlibrary master: %(count) followed by a non-conversion char -> ValueError
            pytest.param('msgid "%(count)s commits behind"\nmsgstr "%(count)개 커밋 뒤처짐"\n', id="bad-conversion"),
            pytest.param('msgid "by %(name)s"\nmsgstr "von %(author)s"\n', id="unknown-name"),
            pytest.param('msgid "%s books"\nmsgstr "%s %s Bücher"\n', id="too-many-positional"),
            pytest.param(
                'msgid "one book"\nmsgid_plural "%(n)s books"\nmsgstr[0] "ein Buch"\nmsgstr[1] "%(m)s Bücher"\n',
                id="plural-form",
            ),
            pytest.param('msgid "a"\nthis is not po\nmsgstr "b"\n', id="syntax"),
            # Jinja's newstyle gettext always applies `% variables`, even with none
            pytest.param('msgid "Edit"\nmsgstr "Modifier (100% gratuit)"\n', id="jinja-bare-percent"),
            # renders the argument dict's repr
            pytest.param('msgid "by %(name)s"\nmsgstr "von %s"\n', id="named-to-positional"),
        ],
    )
    def test_keeps_the_committed_file_when_the_pulled_one_is_unsafe(self, tmp_path, body):
        src, dest = tmp_path / "src", tmp_path / "dest"
        _write_locale(src, "hr", body)
        committed = _write_locale(dest, "hr", self.GOOD)
        before = committed.read_bytes()

        results = i18n.install_translations(str(src), str(dest))

        assert results["hr"], "unsafe file was accepted"
        assert committed.read_bytes() == before

    def test_keeps_committed_on_undecodable_file(self, tmp_path):
        src, dest = tmp_path / "src", tmp_path / "dest"
        (src / "hr").mkdir(parents=True)
        (src / "hr" / "messages.po").write_bytes(PO_HEADER.encode() + b'msgid "a"\nmsgstr "\xff\xfe"\n')
        committed = _write_locale(dest, "hr", self.GOOD)
        before = committed.read_bytes()

        assert i18n.install_translations(str(src), str(dest))["hr"]
        assert committed.read_bytes() == before

    def test_keeps_committed_when_plural_forms_header_does_not_load(self, tmp_path):
        # Babel compiles this, but gettext raises when load_translations loads the .mo.
        # Babel only writes Plural-Forms into the .mo when the catalog has a Language.
        src, dest = tmp_path / "src", tmp_path / "dest"
        (src / "hr").mkdir(parents=True)
        header = PO_HEADER.replace('"Plural-Forms', '"Language: hr\\n"\n"Plural-Forms').replace("plural=(n != 1);", "plural=((n != 1);")
        (src / "hr" / "messages.po").write_text(header + self.GOOD, encoding="utf-8")
        committed = _write_locale(dest, "hr", self.GOOD)
        before = committed.read_bytes()

        assert i18n.install_translations(str(src), str(dest))["hr"]
        assert committed.read_bytes() == before

    def test_untranslated_and_benign_entries_do_not_block_install(self, tmp_path):
        # Empty msgstrs fall back to English at runtime; %(n)d for %(n)s is fine when
        # n is an int; a placeholder-free msgid with a plain or %%-escaped msgstr is fine.
        src, dest = tmp_path / "src", tmp_path / "dest"
        _write_locale(
            src,
            "hr",
            'msgid "%s books"\nmsgstr ""\n'
            'msgid "one"\nmsgid_plural "%s works"\nmsgstr[0] ""\nmsgstr[1] ""\n'
            'msgid "%(n)s people"\nmsgstr "%(n)d ljudi"\n'
            'msgid "Edit"\nmsgstr "Uredi (100%% besplatno)"\n' + self.GOOD,
        )
        dest.mkdir()

        assert i18n.install_translations(str(src), str(dest)) == {"hr": []}

    def test_fuzzy_entries_do_not_block_install(self, tmp_path):
        # Fuzzy entries are never compiled into the .mo, so they cannot crash a render.
        src, dest = tmp_path / "src", tmp_path / "dest"
        _write_locale(src, "hr", '#, fuzzy\nmsgid "by %s"\nmsgstr "od %(link)s"\n' + self.GOOD)
        dest.mkdir()

        assert i18n.install_translations(str(src), str(dest)) == {"hr": []}

    def test_one_bad_language_does_not_stop_the_others(self, tmp_path):
        src, dest = tmp_path / "src", tmp_path / "dest"
        _write_locale(src, "de", self.GOOD)
        _write_locale(src, "hr", 'msgid "by %s"\nmsgstr "od %(link)s"\n')
        dest.mkdir()

        results = i18n.install_translations(str(src), str(dest))

        assert results["de"] == []
        assert results["hr"]
        assert (dest / "de" / "messages.po").exists()
        assert not (dest / "hr").exists()

    def test_source_with_no_languages_is_an_error(self, tmp_path):
        # A layout change upstream must not look like "nothing to update".
        (tmp_path / "src").mkdir()
        with pytest.raises(ValueError, match="no locales"):
            i18n.install_translations(str(tmp_path / "src"), str(tmp_path))


def test_extract_vue_reads_the_script_block():
    source = b"""<template>
    <p>{{ strings.heading }}</p>
</template>

<script>
import { gettext } from './i18n.js';
// NOTE: The page heading.
const heading = gettext('Scan a barcode');
</script>
"""
    found = list(i18n.extract_vue(BytesIO(source), {"gettext": None}, ["NOTE:"], {}))

    assert found == [(8, "gettext", "Scan a barcode", ["NOTE: The page heading."])]


def test_extract_messages_reads_lit_templates_and_vue_scripts(tmp_path, monkeypatch):
    """Calls inside a Lit tagged template are found, and so are a .vue file's (in any-case <script> tags)."""
    source = tmp_path / "components"
    source.mkdir()
    (source / "OlThing.js").write_text("const label = gettext('Outside');\nconst t = html`<b>${gettext('In a template')}</b>`;\n")
    (source / "Thing.vue").write_text("<template><p>{{ x }}</p></template>\n<SCRIPT>\nconst x = gettext('In a script');\n</SCRIPT >\n")
    monkeypatch.setattr(i18n, "root", str(tmp_path))

    i18n.extract_messages([str(source)], verbose=False, skip_untracked=False)

    with open(tmp_path / "messages.pot", "rb") as f:
        assert {message.id for message in read_po(f) if message.id} == {"Outside", "In a template", "In a script"}


def test_extract_vue_rejects_calls_in_the_template():
    """Including after a nested <template>."""
    source = b"<template><div><template v-if='x'><p>a</p></template><p>{{ gettext('Never extracted') }}</p></div></template>\n<script>\nconst x = 1;\n</script>\n"

    with pytest.raises(ValueError, match="not <template>"):
        list(i18n.extract_vue(BytesIO(source), {"gettext": None}, [], {}))


def test_extract_vue_reads_html_strings_in_the_script():
    source = b"<template><p>{{ x }}</p></template>\n<script>\nconst html = '</template>';\nconst x = gettext('In the script');\n</script>\n"

    assert [m[2] for m in i18n.extract_vue(BytesIO(source), {"gettext": None}, [], {})] == ["In the script"]


@pytest.fixture
def clear_javascript_catalog():
    i18n.javascript_catalog.cache_clear()
    yield
    i18n.javascript_catalog.cache_clear()


def test_javascript_msgids_are_the_strings_from_js_and_vue_files(tmp_path, monkeypatch):
    catalog = Catalog()
    catalog.add("Server only", locations=[("openlibrary/plugins/worksearch/code.py", None)])
    catalog.add("Advanced", locations=[("BarcodeScanner.vue", None)])
    catalog.add(("%(count)s list", "%(count)s lists"), locations=[("lit/OlShelfActions.js", None), ("lists.html", None)])
    with open(tmp_path / "messages.pot", "wb") as f:
        write_po(f, catalog)
    monkeypatch.setattr(i18n, "root", str(tmp_path))

    assert i18n._javascript_msgids() == ["Advanced", ("%(count)s list", "%(count)s lists")]


@pytest.mark.parametrize(
    ("lang", "advanced", "list_forms", "expected_list"),
    [
        ("es", "Avanzado", ("%(count)s lista", "%(count)s listas"), {"one": "%(count)s lista", "other": "%(count)s listas"}),
        # Japanese has only the "other" plural category.
        ("ja", "詳細", ("%(count)s 件のリスト",), {"other": "%(count)s 件のリスト"}),
    ],
)
def test_javascript_catalog_has_the_translated_javascript_strings(monkeypatch, clear_javascript_catalog, lang, advanced, list_forms, expected_list):
    catalog = Catalog(locale=lang)
    catalog.add("Advanced", advanced)
    catalog.add(("%(count)s list", "%(count)s lists"), list_forms)
    catalog.add("Untranslated", "")
    mo = BytesIO()
    write_mo(mo, catalog)
    mo.seek(0)
    monkeypatch.setattr(i18n, "load_translations", lambda lang: Translations(mo))
    monkeypatch.setattr(i18n, "_javascript_msgids", lambda: ["Advanced", ("%(count)s list", "%(count)s lists"), "Untranslated"])

    assert i18n.javascript_catalog(lang) == {"Advanced": advanced, "%(count)s list": expected_list}
