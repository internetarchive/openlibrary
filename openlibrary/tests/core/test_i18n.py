import pytest
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


class Test_unwrap_location_comments:
    def test_collapses_a_wrapped_block_to_one_line(self):
        pot = '#: search/authors.html search/lists.html search/subjects.html\n#: work_search.html\nmsgid "Checking Search Inside matches"\nmsgstr ""\n'
        assert i18n._unwrap_location_comments(pot) == (
            '#: search/authors.html search/lists.html search/subjects.html work_search.html\nmsgid "Checking Search Inside matches"\nmsgstr ""\n'
        )

    def test_leaves_single_line_location_comments_untouched(self):
        pot = '#: work_search.html\nmsgid "Sort by"\nmsgstr ""\n'
        assert i18n._unwrap_location_comments(pot) == pot

    def test_does_not_touch_message_text_or_other_comments(self):
        # Long msgid text stays wrapped; only #: lines are joined.
        pot = (
            "#. This is a translator note\n"
            "#: a.html b.html\n"
            "#: c.html\n"
            'msgid ""\n'
            '"A very long message that babel wrapped across two physical "\n'
            '"lines for readability"\n'
            'msgstr ""\n'
        )
        result = i18n._unwrap_location_comments(pot)
        assert "#: a.html b.html c.html\n" in result
        assert "#. This is a translator note\n" in result
        assert '"A very long message that babel wrapped across two physical "\n' in result

    def test_adding_one_file_extends_the_line_instead_of_reflowing(self):
        before = "#: search/authors.html search/lists.html search/subjects.html work_search.html\n"
        after = "#: search/authors.html search/editions.html search/lists.html\n#: search/subjects.html work_search.html\n"
        # The wrapped "after" (what babel would emit) collapses back to a single line
        # whose only change from "before" is the inserted file -- a clean one-line diff.
        assert i18n._unwrap_location_comments(after) == ("#: search/authors.html search/editions.html search/lists.html search/subjects.html work_search.html\n")
        assert i18n._unwrap_location_comments(before) == before
