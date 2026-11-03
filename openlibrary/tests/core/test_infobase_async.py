import pytest

from openlibrary.core import infobase_async


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        {"type": "/type/edition"},
        {"isbn_": "1234567890"},
        {"type": "/type/edition", "isbn_": "1234567890", "limit": "abc"},
        {"type": "/type/edition", "key": "/books/OL1M"},
        {"type": "/type/edition", "title~": "foo*"},
        {"type": "/type/edition", "works.key": "/works/OL1W"},
        {"type": "/type/edition", "isbn_": None},
        {"type": "/type/edition", "isbn_": ["1", "2"]},
    ],
)
async def test_unsupported_queries_raise_before_touching_the_db(query, monkeypatch):
    async def no_db(*args, **kwargs):
        raise AssertionError("should not query the database")

    monkeypatch.setattr(infobase_async, "fetch_val", no_db)
    monkeypatch.setattr(infobase_async, "fetch_all", no_db)
    monkeypatch.setitem(infobase_async._type_ids, "/type/edition", 1)
    monkeypatch.setitem(infobase_async._type_datatypes, "/type/edition", {})

    with pytest.raises(infobase_async.UnsupportedQuery):
        await infobase_async.things(query)
