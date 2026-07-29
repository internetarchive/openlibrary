from io import BytesIO

import pytest
import web
from babel.messages.catalog import Catalog
from babel.messages.pofile import write_po

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
