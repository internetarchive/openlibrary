import pytest

from openlibrary.core.ratings import WorkRatingsSummary
from openlibrary.solr import update
from openlibrary.solr.data_provider import DataProvider, WorkReadingLogSolrSummary

author_counter = 0
edition_counter = 0
work_counter = 0


def make_author(**kw):
    """
    Create a fake author

    :param kw: author data
    :rtype: dict
    """
    global author_counter
    author_counter += 1
    kw.setdefault("key", "/authors/OL%dA" % author_counter)
    kw.setdefault("type", {"key": "/type/author"})
    kw.setdefault("name", "Foo")
    return kw


def make_edition(work=None, **kw):
    """
    Create a fake edition

    :param dict work: Work dict which this is an edition of
    :param kw: edition data
    :rtype: dict
    """
    global edition_counter
    edition_counter += 1
    kw.setdefault("key", "/books/OL%dM" % edition_counter)
    kw.setdefault("type", {"key": "/type/edition"})
    kw.setdefault("title", "Foo")
    if work:
        kw.setdefault("works", [{"key": work["key"]}])
    return kw


def make_work(**kw):
    """
    Create a fake work

    :param kw:
    :rtype: dict
    """
    global work_counter
    work_counter += 1
    kw.setdefault("key", "/works/OL%dW" % work_counter)
    kw.setdefault("type", {"key": "/type/work"})
    kw.setdefault("title", "Foo")
    return kw


class FakeDataProvider(DataProvider):
    """Stub data_provider and methods which are used by build_data."""

    docs: list = []
    docs_by_key: dict = {}

    def __init__(self, docs=None):
        docs = docs or []
        """
        :param list[dict] docs: Documents in the DataProvider
        """
        self.docs = docs
        self.docs_by_key = {doc["key"]: doc for doc in docs}

    def add_docs(self, docs):
        self.docs.extend(docs)
        self.docs_by_key.update({doc["key"]: doc for doc in docs})

    def find_redirects(self, key):
        return []

    async def get_document(self, key):
        return self.docs_by_key.get(key)

    def get_editions_of_work(self, work):
        return [
            doc for doc in self.docs if {"key": work["key"]} in doc.get("works", [])
        ]

    def get_metadata(self, id):
        return {}

    def get_work_ratings(self, work_key: str) -> WorkRatingsSummary | None:
        return None

    def get_work_reading_log(self, work_key: str) -> WorkReadingLogSolrSummary | None:
        return None


class Test_update_keys:
    @classmethod
    def setup_class(cls):
        update.data_provider = FakeDataProvider()

    @pytest.mark.asyncio
    async def test_delete(self):
        update.data_provider.add_docs(
            [
                {'key': '/works/OL23W', 'type': {'key': '/type/delete'}},
                make_author(key='/authors/OL23A', type={'key': '/type/delete'}),
                {'key': '/books/OL23M', 'type': {'key': '/type/delete'}},
            ]
        )
        update_state = await update.update_keys(
            [
                '/works/OL23W',
                '/authors/OL23A',
                '/books/OL23M',
            ],
            update='quiet',
        )
        assert set(update_state.deletes) == {
            '/works/OL23W',
            '/authors/OL23A',
            '/books/OL23M',
        }
        assert update_state.adds == []

    @pytest.mark.asyncio
    async def test_redirects(self):
        update.data_provider.add_docs(
            [
                {
                    'key': '/books/OL23M',
                    'type': {'key': '/type/redirect'},
                    'location': '/books/OL24M',
                },
                {'key': '/books/OL24M', 'type': {'key': '/type/delete'}},
            ]
        )
        update_state = await update.update_keys(['/books/OL23M'], update='quiet')
        assert update_state.deletes == ['/books/OL23M', '/books/OL24M']
        assert update_state.adds == []
