"""Coverstore schema."""

from openlibrary.utils import schema

def get_schema(engine='postgres'):
    s = schema.Schema()
    
    s.add_table('category',
        s.column('id', 'serial', primary_key=True),
        s.column('name', 'string')
    )
    
    s.add_table('cover',
        s.column('id', 'serial', primary_key=True),
        s.column('category_id', 'integer', references='category'),
        s.column('olid', 'string'),
        s.column('filename', 'string'),
        s.column('filename_s', 'string'),
        s.column('filename_m', 'string'),
        s.column('filename_l', 'string'),
        s.column('author', 'string'),
        s.column('ip', 'string'),
        s.column('source_url', 'string'),
        s.column('isbn', 'string'),
        s.column('width', 'integer'),
        s.column('height', 'integer'),
        s.column('archived', 'boolean'),
        s.column('deleted', 'boolean', default=False),
        s.column('created', 'timestamp', default=s.CURRENT_UTC_TIMESTAMP),
        s.column('last_modified', 'timestamp', default=s.CURRENT_UTC_TIMESTAMP),
    )
    
    s.add_index('cover', 'olid')
    s.add_index('cover', 'last_modified')
    s.add_index('cover', 'created')
    s.add_index('cover', 'deleted')
    s.add_index('cover', 'archived')

    s.add_table("log",
        s.column("id", "serial", primary_key=True),
        s.column("cover_id", "integer", references="cover"),
        s.column("action", "text"),
        s.column("timestamp", "timestamp")
    )
    s.add_index("log", "timestamp")

    sql = s.sql(engine)
    if engine == 'sqlite':
        # quick hack to fix bug in openlibrary.utils.schema
        sql = sql.replace('autoincrement primary key', 'primary key autoincrement')
    return sql
    