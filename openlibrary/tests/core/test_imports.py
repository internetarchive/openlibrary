from typing import Final

import pytest
import web

from openlibrary.core.db import get_db
from openlibrary.core.imports import Batch, ImportItem

IMPORT_ITEM_DDL: Final = """
CREATE TABLE import_item (
    id serial primary key,
    batch_id integer,
    status text default 'pending',
    error text,
    ia_id text,
    data text,
    ol_key text,
    comments text,
    UNIQUE (batch_id, ia_id)
);
"""

IMPORT_BATCH_DDL: Final = """
CREATE TABLE import_batch (
    id integer primary key,
    name text,
    submitter text,
    submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

IMPORT_ITEM_DATA: Final = [
    {
        'id': 1,
        'batch_id': 1,
        'ia_id': 'unique_id_1',
        'status': 'pending',
    },
    {
        'id': 2,
        'batch_id': 1,
        'ia_id': 'unique_id_2',
        'status': 'pending',
    },
    {
        'id': 3,
        'batch_id': 2,
        'ia_id': 'unique_id_1',
        'status': 'pending',
    },
]

IMPORT_ITEM_DATA_STAGED: Final = [
    {
        'id': 1,
        'batch_id': 1,
        'ia_id': 'unique_id_1',
        'status': 'staged',
    },
    {
        'id': 2,
        'batch_id': 1,
        'ia_id': 'unique_id_2',
        'status': 'staged',
    },
    {
        'id': 3,
        'batch_id': 2,
        'ia_id': 'unique_id_1',
        'status': 'staged',
    },
]

IMPORT_ITEM_DATA_STAGED_AND_PENDING: Final = [
    {
        'id': 1,
        'batch_id': 1,
        'ia_id': 'idb:unique_id_1',
        'status': 'pending',
    },
    {
        'id': 2,
        'batch_id': 1,
        'ia_id': 'idb:unique_id_2',
        'status': 'staged',
    },
    {
        'id': 3,
        'batch_id': 2,
        'ia_id': 'idb:unique_id_1',
        'status': 'staged',
    },
]


@pytest.fixture(scope="module")
def setup_item_db():
    web.config.db_parameters = {'dbn': 'sqlite', 'db': ':memory:'}
    db = get_db()
    db.query(IMPORT_ITEM_DDL)
    yield db
    db.query('delete from import_item;')


@pytest.fixture
def import_item_db(setup_item_db):
    setup_item_db.multiple_insert('import_item', IMPORT_ITEM_DATA)
    yield setup_item_db
    setup_item_db.query('delete from import_item;')


@pytest.fixture
def import_item_db_staged(setup_item_db):
    setup_item_db.multiple_insert('import_item', IMPORT_ITEM_DATA_STAGED)
    yield setup_item_db
    setup_item_db.query('delete from import_item;')


@pytest.fixture
def import_item_db_staged_and_pending(setup_item_db):
    setup_item_db.multiple_insert('import_item', IMPORT_ITEM_DATA_STAGED_AND_PENDING)
    yield setup_item_db
    setup_item_db.query('delete from import_item;')


class TestImportItem:
    def test_delete(self, import_item_db):
        assert len(list(import_item_db.select('import_item'))) == 3

        ImportItem.delete_items(['unique_id_1'])
        assert len(list(import_item_db.select('import_item'))) == 1

    def test_delete_with_batch_id(self, import_item_db):
        assert len(list(import_item_db.select('import_item'))) == 3

        ImportItem.delete_items(['unique_id_1'], batch_id=1)
        assert len(list(import_item_db.select('import_item'))) == 2

        ImportItem.delete_items(['unique_id_1'], batch_id=2)
        assert len(list(import_item_db.select('import_item'))) == 1

    def test_find_pending_returns_none_with_no_results(self, import_item_db_staged):
        """Try with only staged items in the DB."""
        assert ImportItem.find_pending() is None

    def test_find_pending_returns_pending(self, import_item_db):
        """Try with some pending items now."""
        items = ImportItem.find_pending()
        assert isinstance(items, map)

    @pytest.mark.parametrize(
        'ia_id, expected',
        [
            ('unique_id_1', [1, 3]),
            ('unique_id_2', [2]),
            ('unique_id_4', []),
        ],
    )
    def test_find_staged_or_pending(
        self, import_item_db_staged_and_pending, ia_id, expected
    ):
        """Get some staged and pending items by ia_id identifiers."""
        items = ImportItem.find_staged_or_pending([ia_id], sources=["idb"])
        assert [item['id'] for item in items] == expected


@pytest.fixture(scope="module")
def setup_batch_db():
    web.config.db_parameters = {'dbn': 'sqlite', 'db': ':memory:'}
    db = get_db()
    db.query(IMPORT_BATCH_DDL)
    yield db
    db.query('delete from import_batch;')


class TestBatchItem:
    def test_add_items_legacy(self, setup_batch_db):
        """This tests the legacy format of list[str] for items."""
        legacy_items = ["ocaid_1", "ocaid_2"]
        batch = Batch.new("test-legacy-batch")
        result = batch.normalize_items(legacy_items)
        assert result == [
            {'batch_id': 1, 'ia_id': 'ocaid_1'},
            {'batch_id': 1, 'ia_id': 'ocaid_2'},
        ]
