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
        monkeypatch.setattr(web.webapi, "ctx", web.ctx)

        self._load_fake_context()
        web.ctx.site = MockSite()

    def _load_fake_context(self):
        self.app = web.application()
        self.env = {
            "PATH_INFO": "/", "HTTP_METHOD": "GET",
            "HTTP_ACCEPT_LANGUAGE": "en-US,en;q=0.8,fr;q=0.6,ak;q=0.4,de;q=0.2"
        }
        self.app.load(self.env)

    def test_ungettext(self, monkeypatch):
        self.setup_monkeypatch(monkeypatch)

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


class Test_get_ol_locale:
    @classmethod
    def setup_class(cls):
        ctx = web.storage()
        setattr(web, "ctx", ctx)
        setattr(web.webapi, "ctx", web.ctx)

        cls.app = web.application()
        cls.env = {
            "PATH_INFO": "/", "HTTP_METHOD": "GET",
        }
        cls.app.load(cls.env)
        web.ctx.site = MockSite()

    def test_get_ol_locale(self):
        web.ctx.env['HTTP_ACCEPT_LANGUAGE'] = 'en-US,it;q=0.8,fr;q=0.6,cs;q=0.4,de;q=0.2'

        assert i18n.get_ol_locale() == 'fr'

    def test_get_ol_locale_no_header(self):
        del web.ctx.env['HTTP_ACCEPT_LANGUAGE']

        assert i18n.get_ol_locale() == 'en'

    def test_get_ol_locale_no_support(self):
        web.ctx.env['HTTP_ACCEPT_LANGUAGE'] = 'en-US,it;q=0.8,gr;q=0.6,am;q=0.4,be;q=0.2'

        assert i18n.get_ol_locale() == 'en'

    def test_get_ol_locale_first_preference_match(self):
        web.ctx.env['HTTP_ACCEPT_LANGUAGE'] = 'es,de;q=0.8,fr;q=0.6,cs;q=0.4,am;q=0.2'

        assert i18n.get_ol_locale() == 'es'

    def test_get_ol_locale_second_preference_match(self):
        web.ctx.env['HTTP_ACCEPT_LANGUAGE'] = 'am,de;q=0.8,fr;q=0.6,cs;q=0.4,be;q=0.2'

        assert i18n.get_ol_locale() == 'de'

    def test_get_ol_locale_final_preference_match(self):
        web.ctx.env['HTTP_ACCEPT_LANGUAGE'] = 'it,am;q=0.8,be;q=0.6,gr;q=0.4,cs;q=0.2'

        assert i18n.get_ol_locale() == 'cs'
