"""Labels on the import system -- lightweight key/value metadata on import
batches and items (#14751).

Labels are **not** GitHub issue labels. They let the import system categorize
and *query* what flows through it. The motivating uses (from #14751 / #14750):

* mark whether a batch/item is an **import** or an **edit** (``type=import`` /
  ``type=edit``),
* tag the **source app** (``source_app=openshelf``) and a **pseudonymous
  originating-patron id** (``patron=<app-user-id>``), so edits are queryable and
  bulk-repairable by originating user,
* general categorization/filtering for the import review and submission UIs.

Each label is a ``(label_key, label_value)`` pair attached to exactly one target
-- a batch *or* an import item. A target may carry several labels, and the same
key may appear more than once (e.g. two free-form category tags); what is unique
is the whole ``(target, key, value)`` triple, so re-applying a label is
idempotent.

Storage lives in the ``import_label`` table declared in
``openlibrary/core/schema.sql``. See that file for why the target columns are
plain integers rather than foreign keys, and
``openlibrary/tests/core/test_import_labels.py`` for the production DDL and the
drift check against it.

This is new database code, so it goes through the async psycopg3 pool
(``openlibrary.core.async_db``) as the project requires. The legacy, synchronous
import pipeline (``openlibrary/core/imports.py``, ``batch_imports.py``,
``scripts/manage-imports.py``) reaches it through the ``*_sync`` bridges, which
run the coroutine on ``async_bridge``'s loop. This mirrors the reference
migration in ``openlibrary/core/yearly_reading_goals.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from openlibrary.core.async_db import class_row, connection, execute, fetch_all
from openlibrary.utils.async_utils import async_bridge


@dataclass(frozen=True, slots=True)
class ImportLabel:
    """One row of the ``import_label`` table."""

    id: int
    batch_id: int | None
    import_item_id: int | None
    label_key: str
    label_value: str


def _one_target(batch_id: int | None, import_item_id: int | None) -> tuple[str, int]:
    """Validate that exactly one target is given; return its column and id.

    The database CHECK enforces this too, but validating in Python turns a
    caller mistake into a clear ``ValueError`` at the call site instead of an
    opaque integrity error from deep in the driver.
    """
    if (batch_id is None) == (import_item_id is None):
        raise ValueError("Exactly one of batch_id or import_item_id must be given")
    return ("batch_id", batch_id) if batch_id is not None else ("import_item_id", import_item_id)  # type: ignore[return-value]


class ImportLabels:
    """Read/write access to labels on import batches and items."""

    TABLENAME = "import_label"

    # --- Write ---------------------------------------------------------------

    @classmethod
    async def add(
        cls,
        label_key: str,
        label_value: str,
        *,
        batch_id: int | None = None,
        import_item_id: int | None = None,
    ) -> None:
        """Attach one label to one target (a batch or an item).

        Idempotent: re-adding the same ``(target, key, value)`` is a no-op, so
        callers can label on every submit without accumulating duplicate rows.
        """
        column, target_id = _one_target(batch_id, import_item_id)
        query = f"INSERT INTO {cls.TABLENAME} ({column}, label_key, label_value) VALUES (%(target_id)s, %(label_key)s, %(label_value)s) ON CONFLICT DO NOTHING"
        await execute(query, {"target_id": target_id, "label_key": label_key, "label_value": label_value})

    @classmethod
    async def add_many(
        cls,
        labels: Mapping[str, str],
        *,
        batch_id: int | None = None,
        import_item_id: int | None = None,
    ) -> None:
        """Attach several labels (a ``{key: value}`` mapping) to one target."""
        _one_target(batch_id, import_item_id)
        for label_key, label_value in labels.items():
            await cls.add(label_key, label_value, batch_id=batch_id, import_item_id=import_item_id)

    @classmethod
    async def set_single(
        cls,
        label_key: str,
        label_value: str,
        *,
        batch_id: int | None = None,
        import_item_id: int | None = None,
    ) -> None:
        """Set a *single-valued* key on one target, replacing any prior value.

        Some keys are naturally single-valued -- ``type`` is exactly one of
        ``import``/``edit``, a submission has one ``source_app``. The schema does
        not constrain this (a key may hold several values in general; see the
        class docstring), so single-valuedness is an app-level convention, applied
        here by dropping the key's existing rows for this target and adding the
        new one in **one transaction** -- no window where the key is missing, and
        no mid-failure state that keeps the old value dropped without the new one.

        Scope of the guarantee: this is last-write-wins for *serial* callers. It
        does **not** serialize two writers racing on the same ``(target, key)``;
        because the unique index is on ``(target, key, value)``, two concurrent
        ``set_single`` of different values can both survive, leaving the key
        multi-valued. No caller in this change does that (a submission sets its
        own item's ``type`` once); a future caller that needs a hard guarantee
        should add a partial unique index on ``(target, label_key)`` for the
        single-valued keys rather than rely on this method.
        """
        column, target_id = _one_target(batch_id, import_item_id)
        async with connection() as conn:
            await conn.execute(
                f"DELETE FROM {cls.TABLENAME} WHERE {column} = %(target_id)s AND label_key = %(label_key)s",
                {"target_id": target_id, "label_key": label_key},
            )
            await conn.execute(
                f"INSERT INTO {cls.TABLENAME} ({column}, label_key, label_value) VALUES (%(target_id)s, %(label_key)s, %(label_value)s) ON CONFLICT DO NOTHING",
                {"target_id": target_id, "label_key": label_key, "label_value": label_value},
            )

    # --- Read ----------------------------------------------------------------

    @classmethod
    async def for_target(
        cls,
        *,
        batch_id: int | None = None,
        import_item_id: int | None = None,
    ) -> dict[str, list[str]]:
        """Every label on one target, grouped ``{key: [value, ...]}``.

        Values for a key are sorted for a stable return, so callers (and tests)
        do not depend on row insertion order.
        """
        column, target_id = _one_target(batch_id, import_item_id)
        query = f"SELECT label_key, label_value FROM {cls.TABLENAME} WHERE {column} = %(target_id)s ORDER BY label_key, label_value"
        rows = await fetch_all(query, {"target_id": target_id})
        grouped: dict[str, list[str]] = {}
        for row in rows:
            grouped.setdefault(row["label_key"], []).append(row["label_value"])
        return grouped

    @classmethod
    async def _target_ids_with(
        cls,
        column: str,
        label_key: str,
        label_value: str | None,
    ) -> list[int]:
        query = f"SELECT {column} AS target_id FROM {cls.TABLENAME} WHERE {column} IS NOT NULL AND label_key = %(label_key)s"
        params: dict[str, object] = {"label_key": label_key}
        if label_value is not None:
            query += " AND label_value = %(label_value)s"
            params["label_value"] = label_value
        query += f" ORDER BY {column}"
        rows = await fetch_all(query, params)
        return [row["target_id"] for row in rows]

    @classmethod
    async def batch_ids_with(cls, label_key: str, label_value: str | None = None) -> list[int]:
        """Batch ids carrying ``label_key`` (optionally narrowed to one value)."""
        return await cls._target_ids_with("batch_id", label_key, label_value)

    @classmethod
    async def item_ids_with(cls, label_key: str, label_value: str | None = None) -> list[int]:
        """Import-item ids carrying ``label_key`` (optionally narrowed to one value).

        This is the #14750 "query + repair by originating patron" entry point:
        ``item_ids_with("patron", "<app-user-id>")`` returns every item that one
        patron originated, ready to re-queue or revert.
        """
        return await cls._target_ids_with("import_item_id", label_key, label_value)

    @classmethod
    async def select_for_target(
        cls,
        *,
        batch_id: int | None = None,
        import_item_id: int | None = None,
    ) -> list[ImportLabel]:
        """Full label rows for one target (when the ids/created are needed)."""
        column, target_id = _one_target(batch_id, import_item_id)
        query = f"SELECT id, batch_id, import_item_id, label_key, label_value FROM {cls.TABLENAME} WHERE {column} = %(target_id)s ORDER BY label_key, label_value"
        return await fetch_all(query, {"target_id": target_id}, row_factory=class_row(ImportLabel))

    # --- Delete --------------------------------------------------------------

    @classmethod
    async def delete_for_target(
        cls,
        *,
        batch_id: int | None = None,
        import_item_id: int | None = None,
    ) -> None:
        """Remove every label on one target.

        The target columns are not foreign keys (see schema.sql), so deleting a
        batch or item does not cascade to its labels; callers that delete a
        target call this to keep labels from outliving it.
        """
        column, target_id = _one_target(batch_id, import_item_id)
        await execute(f"DELETE FROM {cls.TABLENAME} WHERE {column} = %(target_id)s", {"target_id": target_id})

    # --- Sync bridges for the legacy import pipeline -------------------------

    @classmethod
    def add_sync(
        cls,
        label_key: str,
        label_value: str,
        *,
        batch_id: int | None = None,
        import_item_id: int | None = None,
    ) -> None:
        async_bridge.run(cls.add(label_key, label_value, batch_id=batch_id, import_item_id=import_item_id))

    @classmethod
    def add_many_sync(
        cls,
        labels: Mapping[str, str],
        *,
        batch_id: int | None = None,
        import_item_id: int | None = None,
    ) -> None:
        async_bridge.run(cls.add_many(labels, batch_id=batch_id, import_item_id=import_item_id))

    @classmethod
    def set_single_sync(
        cls,
        label_key: str,
        label_value: str,
        *,
        batch_id: int | None = None,
        import_item_id: int | None = None,
    ) -> None:
        async_bridge.run(cls.set_single(label_key, label_value, batch_id=batch_id, import_item_id=import_item_id))

    @classmethod
    def for_target_sync(
        cls,
        *,
        batch_id: int | None = None,
        import_item_id: int | None = None,
    ) -> dict[str, list[str]]:
        return async_bridge.run(cls.for_target(batch_id=batch_id, import_item_id=import_item_id))

    @classmethod
    def batch_ids_with_sync(cls, label_key: str, label_value: str | None = None) -> list[int]:
        return async_bridge.run(cls.batch_ids_with(label_key, label_value))

    @classmethod
    def item_ids_with_sync(cls, label_key: str, label_value: str | None = None) -> list[int]:
        return async_bridge.run(cls.item_ids_with(label_key, label_value))

    @classmethod
    def delete_for_target_sync(
        cls,
        *,
        batch_id: int | None = None,
        import_item_id: int | None = None,
    ) -> None:
        async_bridge.run(cls.delete_for_target(batch_id=batch_id, import_item_id=import_item_id))
