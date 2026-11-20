from pathlib import Path

import pytest

from openlibrary.core import async_db, infobase_async


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_redirect_location_reads_only_the_current_redirect(pg_db):
    # pg_db loads the feature tables; thing and data belong to Infobase.
    schema = Path(infobase_async.__file__).with_name("infobase_schema.sql")
    async with async_db.connection() as conn:
        await conn.execute(schema.read_text())
        await conn.execute("""
            INSERT INTO thing (id, key, type, latest_revision) VALUES
                (1, '/type/redirect', NULL, 1),
                (2, '/type/delete', NULL, 1),
                (3, '/short', 1, 2),
                (4, '/deleted', 2, 1)
        """)
        await conn.execute("""
            INSERT INTO data (thing_id, revision, data) VALUES
                (3, 1, '{"location": "/old"}'),
                (3, 2, '{"location": "/new"}'),
                (4, 1, '{"location": "/stale"}')
        """)

    assert await infobase_async.get_redirect_location("/short") == "/new"
    assert await infobase_async.get_redirect_location("/deleted") is None
    assert await infobase_async.get_redirect_location("/missing") is None
