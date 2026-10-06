"""Connection and cursor fakes for the ``async_db`` helper tests.

Model tests patch the helpers themselves (``fetch_all``, ``fetch_one``,
``execute``, ``fetch_val``) and assert the query and params they pass, so
they never see a connection. These fakes are for the tests one level
down -- what the helpers themselves do with a connection: record executed
queries, hand back canned rows, and commit on clean block exit.

``FakeConnectionContext`` is what ``patch(..., return_value=...)`` needs to
stand in for the ``async with connection() as conn`` block. It commits when
the block exits cleanly and skips the commit when it exits with an error,
which is the commit half of the transaction semantics ``psycopg_pool``'s
``pool.connection()`` gives real connections.

``FakeCursor`` implements the sliver of the psycopg row protocol that
``psycopg.rows`` row factories read: ``cursor.pgresult`` (``status``,
``nfields``, ``fname(i)`` returning bytes) and ``cursor._encoding``. That
is deliberate white-box emulation of psycopg internals -- it lets tests run
the *real* ``class_row(Model)`` factory against the fake, so row mapping is
exercised the same way production does it. Expect to maintain it if psycopg
changes the protocol (``psycopg.rows._get_names`` is today's reader).
"""

from collections.abc import Sequence

from psycopg.rows import TUPLES_OK


class FakeResult:
    """Column metadata of a fake result set -- what ``cursor.pgresult`` is."""

    status = TUPLES_OK

    def __init__(self, columns: Sequence[str]):
        self._columns = tuple(column.encode() for column in columns)
        self.nfields = len(self._columns)

    def fname(self, index: int) -> bytes:
        return self._columns[index]


class FakeCursor:
    """A cursor handing back canned ``rows``, mapped through ``row_factory``.

    Without a ``row_factory`` (the ``conn.execute()`` path), rows are
    returned as-is: dicts for dict-shaped queries, or the raw value
    sequence for anything else.
    """

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
    """Records executed queries and hands back ``FakeCursor`` results.

    ``rows`` are the canned results; ``columns`` are the SELECT's column
    names, read only when a row factory like ``class_row`` maps rows by
    name.
    """

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
    """The ``async with connection() as conn`` block for a ``FakeConnection``."""

    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            await self.conn.commit()
        return False
