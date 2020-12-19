import web
from openlibrary.mocks.mock_infobase import MockSite

# The i18n module should be moved to core.
from openlibrary import i18n


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
        self._load_fake_context()

        web.ctx.site = MockSite()
        monkeypatch.setattr(web, "setcookie", self._setcookie)

    def _load_fake_context(self):
        app = web.application()
        env = {"PATH_INFO": "/", "HTTP_METHOD": "GET"}
        app.load(env)

    def _setcookie(self, name, value):
        self.cookie = dict(name=name, value=value)

    def test_ungettext(self, monkeypatch):
        self.setup_monkeypatch(monkeypatch)

        web.setcookie('i18n_code', 'es')

        i18n.ungettext("book", "books", 1) == "book"
        i18n.ungettext("book", "books", 2) == "books"

        web.ctx.lang = 'fr'
        self.d.init('fr', {
            'book': 'libre',
            'books': 'libres',
        })

        i18n.ungettext("book", "books", 1) == "libre"
        i18n.ungettext("book", "books", 2) == "libres"

        web.ctx.lang = 'te'
        i18n.ungettext("book", "books", 1) == "book"
        i18n.ungettext("book", "books", 2) == "books"

    def test_ungettext_with_args(self, monkeypatch):
        self.setup_monkeypatch(monkeypatch)

        i18n.ungettext("one book", "%(n)d books", 1, n=1) == "one book"
        i18n.ungettext("one book", "%(n)d books", 2, n=2) == "2 books"

        web.ctx.lang = 'fr'
        self.d.init('fr', {
            'one book': 'un libre',
            '%(n)d books': '%(n)d libres',
        })

        i18n.ungettext("one book", "%(n)d books", 1, n=1) == "un libre"
        i18n.ungettext("one book", "%(n)d books", 2, n=2) == "2 libres"
