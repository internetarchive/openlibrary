"""Connection and cursor fakes for the ``async_db`` helper tests.

Model tests patch the helpers and never see a connection. These fakes cover
what the helpers do with one: record queries, return canned rows, and commit
on clean block exit. ``FakeCursor`` emulates the ``pgresult`` bits that
``class_row`` reads, so tests run the real row factory.
"""

from collections.abc import Sequence

from psycopg.rows import TUPLES_OK


class FakeResult:
    """Column metadata behind ``cursor.pgresult``."""

    status = TUPLES_OK

    def __init__(self, columns: Sequence[str]):
        self._columns = tuple(column.encode() for column in columns)
        self.nfields = len(self._columns)

    def fname(self, index: int) -> bytes:
        return self._columns[index]


class FakeCursor:
    """Cursor returning canned ``rows``, mapped through ``row_factory``."""

    def __init__(self, connection, rows=None, row_factory=None):
        self.connection = connection
        self.rows = rows or []
        self.pgresult = FakeResult(connection.columns)
        self._encoding = "utf-8"
        self._row_maker = row_factory(self) if row_factory is not None else None
        self.fetchall_calls = 0
        self.fetchone_calls = 0

    async def execute(self, query, params=None):
        self.connection.executions.append((query, params))
        return self

    async def fetchall(self):
        self.fetchall_calls += 1
        if self._row_maker is None:
            return self.rows
        return [self._row_maker(row) for row in self.rows]

    async def fetchone(self):
        self.fetchone_calls += 1
        if not self.rows:
            return None
        return self._row_maker(self.rows[0]) if self._row_maker is not None else self.rows[0]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    """Records queries and hands back ``FakeCursor`` results."""

    def __init__(self, rows=None, columns=()):
        self.executions = []
        self.committed = False
        self.columns = tuple(columns)
        self._cursor = FakeCursor(self, rows)

    async def execute(self, query, params=None):
        self.executions.append((query, params))
        return self._cursor

    def cursor(self, **kwargs):
        return FakeCursor(self, self._cursor.rows, kwargs.get("row_factory"))

    async def commit(self):
        self.committed = True


class FakeConnectionContext:
    """Stands in for ``async with connection() as conn``."""

    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            await self.conn.commit()
        return False
