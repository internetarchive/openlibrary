"""Unit and integration tests for the async import-labels model (#14751).

Unit tests patch the ``async_db`` helpers and check query text, params, and the
exactly-one-target validation. Integration tests (``TestImportLabelsIntegration``)
run the same methods against real postgres loaded from ``core/schema.sql``, so
the CHECK constraint, the partial-unique idempotency, and the query paths are
exercised against the shape a fresh install actually gets. The drift-assert class
pins the shipped DDL. See ``docs/core/database.md`` for the pattern.
"""

import os
import re
from types import SimpleNamespace
from typing import Final
from unittest.mock import AsyncMock, patch

import pytest
from psycopg.errors import CheckViolation

import openlibrary.core.import_labels as il
from openlibrary.core.async_db import execute
from openlibrary.core.import_labels import ImportLabel, ImportLabels

# The DDL that has actually been executed against production/staging by an
# operator (Open Library has no DDL-migration mechanism). ``schema.sql`` is where
# a *fresh* install gets the table; ``TestTheShippedSchemaHasTheTable`` compares
# the two so they cannot drift -- the tests passing against a shape a fresh
# install never gets is the exact failure the provider_tokens table hit.
POSTGRES_DDL: Final = """
CREATE TABLE import_label (
    id serial primary key,
    batch_id integer default null,
    import_item_id integer default null,
    label_key text not null,
    label_value text not null,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    CONSTRAINT import_label_one_target CHECK (
        (batch_id IS NOT NULL)::int + (import_item_id IS NOT NULL)::int = 1
    )
);
CREATE UNIQUE INDEX import_label_batch_uniq ON import_label (batch_id, label_key, label_value) WHERE batch_id IS NOT NULL;
CREATE UNIQUE INDEX import_label_item_uniq ON import_label (import_item_id, label_key, label_value) WHERE import_item_id IS NOT NULL;
CREATE INDEX import_label_lookup ON import_label (label_key, label_value);
"""

SCHEMA_SQL = os.path.join(os.path.dirname(il.__file__), "schema.sql")


@pytest.fixture
def helpers():
    with (
        patch("openlibrary.core.import_labels.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.import_labels.execute", new_callable=AsyncMock) as execute,
    ):
        yield SimpleNamespace(fetch_all=fetch_all, execute=execute)


# --- Unit tests (no postgres required) ------------------------------------------


@pytest.mark.asyncio
async def test_add_to_batch_builds_idempotent_insert(helpers):
    await ImportLabels.add("source_app", "openshelf", batch_id=7)

    (query, params), _ = helpers.execute.await_args
    assert query.startswith("INSERT INTO import_label (batch_id, label_key, label_value)")
    assert "ON CONFLICT DO NOTHING" in query
    assert params == {"target_id": 7, "label_key": "source_app", "label_value": "openshelf"}


@pytest.mark.asyncio
async def test_add_to_item_targets_the_item_column(helpers):
    await ImportLabels.add("patron", "abc123", import_item_id=42)

    (query, params), _ = helpers.execute.await_args
    assert query.startswith("INSERT INTO import_label (import_item_id, label_key, label_value)")
    assert params == {"target_id": 42, "label_key": "patron", "label_value": "abc123"}


@pytest.mark.asyncio
async def test_add_rejects_no_target(helpers):
    with pytest.raises(ValueError, match="Exactly one of batch_id or import_item_id"):
        await ImportLabels.add("type", "import")
    helpers.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_rejects_both_targets(helpers):
    with pytest.raises(ValueError, match="Exactly one of batch_id or import_item_id"):
        await ImportLabels.add("type", "import", batch_id=1, import_item_id=2)
    helpers.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_single_deletes_then_inserts(helpers):
    await ImportLabels.set_single("type", "edit", import_item_id=42)

    delete_call, insert_call = helpers.execute.await_args_list
    (delete_query, delete_params), _ = delete_call
    assert delete_query.startswith("DELETE FROM import_label WHERE import_item_id = %(target_id)s AND label_key")
    assert delete_params == {"target_id": 42, "label_key": "type"}
    (insert_query, _insert_params), _ = insert_call
    assert insert_query.startswith("INSERT INTO import_label")


@pytest.mark.asyncio
async def test_item_ids_with_value_filters_on_key_and_value(helpers):
    helpers.fetch_all.return_value = [{"target_id": 42}, {"target_id": 43}]

    ids = await ImportLabels.item_ids_with("patron", "abc123")

    assert ids == [42, 43]
    (query, params), _ = helpers.fetch_all.await_args
    assert "import_item_id IS NOT NULL" in query
    assert "label_key = %(label_key)s" in query
    assert "label_value = %(label_value)s" in query
    assert params == {"label_key": "patron", "label_value": "abc123"}


@pytest.mark.asyncio
async def test_item_ids_with_omits_value_clause_when_value_is_none(helpers):
    helpers.fetch_all.return_value = []

    await ImportLabels.item_ids_with("patron")

    (query, params), _ = helpers.fetch_all.await_args
    assert "label_value" not in query
    assert params == {"label_key": "patron"}


@pytest.mark.asyncio
async def test_for_target_groups_values_by_key(helpers):
    helpers.fetch_all.return_value = [
        {"label_key": "category", "label_value": "fiction"},
        {"label_key": "category", "label_value": "poetry"},
        {"label_key": "type", "label_value": "import"},
    ]

    grouped = await ImportLabels.for_target(batch_id=7)

    assert grouped == {"category": ["fiction", "poetry"], "type": ["import"]}


# --- Integration tests (real postgres, marked `integration`) --------------------


@pytest.mark.integration
class TestImportLabelsIntegration:
    @pytest.mark.asyncio
    async def test_add_and_read_back_for_batch(self, pg_db):
        await ImportLabels.add("source_app", "openshelf", batch_id=1)
        await ImportLabels.add("type", "import", batch_id=1)

        assert await ImportLabels.for_target(batch_id=1) == {
            "source_app": ["openshelf"],
            "type": ["import"],
        }

    @pytest.mark.asyncio
    async def test_add_is_idempotent(self, pg_db):
        await ImportLabels.add("type", "edit", import_item_id=5)
        await ImportLabels.add("type", "edit", import_item_id=5)

        rows = await ImportLabels.select_for_target(import_item_id=5)
        assert len(rows) == 1
        assert isinstance(rows[0], ImportLabel)

    @pytest.mark.asyncio
    async def test_same_key_value_on_batch_and_item_coexist(self, pg_db):
        # NULL != NULL means a plain UNIQUE would wrongly merge these; the two
        # partial-unique indexes keep them distinct.
        await ImportLabels.add("type", "import", batch_id=1)
        await ImportLabels.add("type", "import", import_item_id=1)

        assert await ImportLabels.batch_ids_with("type", "import") == [1]
        assert await ImportLabels.item_ids_with("type", "import") == [1]

    @pytest.mark.asyncio
    async def test_item_ids_with_finds_every_patron_item(self, pg_db):
        # The #14750 "query + repair by originating patron" entry point.
        await ImportLabels.add("patron", "p1", import_item_id=10)
        await ImportLabels.add("patron", "p1", import_item_id=11)
        await ImportLabels.add("patron", "p2", import_item_id=12)

        assert await ImportLabels.item_ids_with("patron", "p1") == [10, 11]
        assert await ImportLabels.item_ids_with("patron") == [10, 11, 12]

    @pytest.mark.asyncio
    async def test_set_single_replaces_prior_value(self, pg_db):
        await ImportLabels.set_single("type", "import", import_item_id=5)
        await ImportLabels.set_single("type", "edit", import_item_id=5)

        assert await ImportLabels.for_target(import_item_id=5) == {"type": ["edit"]}

    @pytest.mark.asyncio
    async def test_add_many_sets_several_keys(self, pg_db):
        await ImportLabels.add_many({"source_app": "openshelf", "type": "edit"}, import_item_id=9)

        assert await ImportLabels.for_target(import_item_id=9) == {
            "source_app": ["openshelf"],
            "type": ["edit"],
        }

    @pytest.mark.asyncio
    async def test_delete_for_target_removes_only_that_target(self, pg_db):
        await ImportLabels.add("type", "import", batch_id=1)
        await ImportLabels.add("type", "import", import_item_id=1)

        await ImportLabels.delete_for_target(batch_id=1)

        assert await ImportLabels.for_target(batch_id=1) == {}
        assert await ImportLabels.for_target(import_item_id=1) == {"type": ["import"]}

    @pytest.mark.asyncio
    async def test_check_constraint_rejects_no_target_at_the_db(self, pg_db):
        # Defence in depth: even if a caller bypasses _one_target, the DB refuses
        # a row with neither target. Exercised via a raw insert.
        with pytest.raises(CheckViolation):
            await execute(
                "INSERT INTO import_label (label_key, label_value) VALUES (%(k)s, %(v)s)",
                {"k": "type", "v": "import"},
            )


# --- The shipped schema really has this table -----------------------------------


class TestTheShippedSchemaHasTheTable:
    """A fresh install must get ``import_label`` from ``schema.sql``.

    Two copies of a DDL drift silently and in the worst direction: the tests keep
    passing against the shape they created while a fresh install gets a different
    table. These assertions run with no database and are the only thing tying the
    executed DDL to what ships.
    """

    @staticmethod
    def _schema_text() -> str:
        with open(SCHEMA_SQL) as handle:
            return handle.read()

    @staticmethod
    def _create_table(text: str) -> str:
        match = re.search(r"^CREATE TABLE import_label \(.*?^\);", text, re.DOTALL | re.MULTILINE)
        assert match, f"no `CREATE TABLE import_label` in {SCHEMA_SQL}"
        return match.group(0)

    @staticmethod
    def _normalised(ddl: str) -> str:
        return re.sub(r"\s+", " ", ddl).strip()

    def test_schema_sql_declares_the_table(self):
        assert "import_label" in self._schema_text()

    def test_it_is_the_same_table_the_tests_execute(self):
        shipped = self._create_table(self._schema_text())
        expected = self._create_table(POSTGRES_DDL)
        assert self._normalised(shipped) == self._normalised(expected)

    def test_the_one_target_check_is_declared(self):
        """Without the CHECK, a row could target both a batch and an item, or
        neither -- the exactly-one-target invariant the model relies on."""
        assert "import_label_one_target" in self._schema_text()

    def test_the_partial_unique_indexes_are_declared(self):
        """Idempotent ``add`` (``ON CONFLICT DO NOTHING``) needs these; a plain
        UNIQUE over nullable targets would not dedupe (NULL != NULL)."""
        text = self._schema_text()
        assert "import_label_batch_uniq" in text
        assert "import_label_item_uniq" in text

    def test_the_lookup_index_is_declared(self):
        """The query path -- find every target carrying label X -- is served by
        the (label_key, label_value) index."""
        assert "import_label_lookup" in self._schema_text()
