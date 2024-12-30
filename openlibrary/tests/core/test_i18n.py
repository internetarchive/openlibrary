import web

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
    def setup_monkeypatch(self, monkeypatch):
        self.d = MockLoadTranslations()
        ctx = web.storage()

        monkeypatch.setattr(i18n, "load_translations", self.d)
        monkeypatch.setattr(web, "ctx", ctx)
        monkeypatch.setattr(web.webapi, "ctx", web.ctx)

        self._load_fake_context()
        web.ctx.lang = 'en'
        web.ctx.site = MockSite()

    def _load_fake_context(self):
        self.app = web.application()
        self.env = {
            "PATH_INFO": "/",
            "HTTP_METHOD": "GET",
        }
        self.app.load(self.env)

    def test_ungettext(self, monkeypatch):
        self.setup_monkeypatch(monkeypatch)

        assert i18n.ungettext("book", "books", 1) == "book"
        assert i18n.ungettext("book", "books", 2) == "books"

        web.ctx.lang = 'fr'
        self.d.init(
            'fr',
            {
                'book': 'libre',
                'books': 'libres',
            },
        )

        assert i18n.ungettext("book", "books", 1) == "libre"
        assert i18n.ungettext("book", "books", 2) == "libres"

        web.ctx.lang = 'te'
        assert i18n.ungettext("book", "books", 1) == "book"
        assert i18n.ungettext("book", "books", 2) == "books"

    def test_ungettext_with_args(self, monkeypatch):
        self.setup_monkeypatch(monkeypatch)

        assert i18n.ungettext("one book", "%(n)d books", 1, n=1) == "one book"
        assert i18n.ungettext("one book", "%(n)d books", 2, n=2) == "2 books"

        web.ctx.lang = 'fr'
        self.d.init(
            'fr',
            {
                'one book': 'un libre',
                '%(n)d books': '%(n)d libres',
            },
        )

        assert i18n.ungettext("one book", "%(n)d books", 1, n=1) == "un libre"
        assert i18n.ungettext("one book", "%(n)d books", 2, n=2) == "2 libres"
