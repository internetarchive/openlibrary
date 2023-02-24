import web

from openlibrary.core.db import get_db
from openlibrary.core.imports import ImportItem


class TestImportItem:
    IMPORT_ITEM_DDL = """
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

    IMPORT_ITEM_DATA = [
        {
            'id': 1,
            'batch_id': 1,
            'ia_id': 'unique_id_1',
        },
        {
            'id': 2,
            'batch_id': 1,
            'ia_id': 'unique_id_2',
        },
        {
            'id': 3,
            'batch_id': 2,
            'ia_id': 'unique_id_1',
        },
    ]

    @classmethod
    def setup_class(cls):
        web.config.db_parameters = dict(dbn='sqlite', db=':memory:')
        db = get_db()
        db.query(cls.IMPORT_ITEM_DDL)

    @classmethod
    def teardown_class(cls):
        db = get_db()
        db.query('delete from import_item;')

    def setup_method(self):
        self.db = get_db()
        self.db.multiple_insert('import_item', self.IMPORT_ITEM_DATA)

    def teardown_method(self):
        self.db.query('delete from import_item;')

    def test_delete(self):
        assert len(list(self.db.select('import_item'))) == 3

        ImportItem.delete_items(['unique_id_1'])
        assert len(list(self.db.select('import_item'))) == 1

    def test_delete_with_batch_id(self):
        assert len(list(self.db.select('import_item'))) == 3

        ImportItem.delete_items(['unique_id_1'], batch_id=1)
        assert len(list(self.db.select('import_item'))) == 2

        ImportItem.delete_items(['unique_id_1'], batch_id=2)
        assert len(list(self.db.select('import_item'))) == 1
