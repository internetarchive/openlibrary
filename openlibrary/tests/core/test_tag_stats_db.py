import pytest

from openlibrary.admin.numbers import count_tagged_works
from openlibrary.core.async_db import execute
from openlibrary.core.schema import get_schema


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tagged_works_counts_distinct_work_references_by_tag_field(pg_db):
    await execute(get_schema().sql())
    await execute(
        """
        INSERT INTO thing (id, key, type) VALUES
            (1, '/type/work', NULL), (2, '/type/edition', NULL), (3, '/type/tag', NULL),
            (4, '/works/OL1W', 1), (5, '/works/OL2W', 1),
            (6, '/tags/OL1T', 3), (7, '/tags/OL2T', 3);
        INSERT INTO property (id, type, name) VALUES
            (1, 1, 'genres'), (2, 1, 'subgenres'), (3, 1, 'subjects'), (4, 2, 'awards'), (5, 1, 'awards');
        INSERT INTO work_ref (thing_id, key_id, value) VALUES (4, 1, 6), (4, 1, 7), (4, 2, 6), (4, 3, 6);
        INSERT INTO edition_ref (thing_id, key_id, value) VALUES (4, 4, 6);
        INSERT INTO work_str (thing_id, key_id, value) VALUES (5, 1, 'Classic'), (5, 5, 'An award');
        """
    )

    assert await count_tagged_works() == {
        "genres": 1,
        "subgenres": 1,
        "literary_forms": 0,
        "audiences": 0,
        "content_warnings": 0,
        "content_formats": 0,
        "awards": 0,
    }
