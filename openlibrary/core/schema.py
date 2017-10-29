"""Infobase schema for Open Library
"""
from infogami.infobase import dbstore
import web

def get_schema():
    schema = dbstore.Schema()
    schema.add_table_group('type', '/type/type')
    schema.add_table_group('type', '/type/property')
    schema.add_table_group('type', '/type/backreference')
    schema.add_table_group('user', '/type/user')
    schema.add_table_group('user', '/type/usergroup')
    schema.add_table_group('user', '/type/permission')

    datatypes = ["str", "int", "ref", "boolean"]

    schema.add_table_group('edition', '/type/edition', datatypes)
    schema.add_table_group('author', '/type/author', datatypes)
    schema.add_table_group('scan', '/type/scan_location', datatypes)
    schema.add_table_group('scan', '/type/scan_record', datatypes)

    schema.add_table_group('work', '/type/work', datatypes)
    schema.add_table_group('publisher', '/type/publisher', datatypes)
    schema.add_table_group('subject', '/type/subject', datatypes)

    schema.add_seq('/type/edition', '/books/OL%dM')
    schema.add_seq('/type/author', '/authors/OL%dA')

    schema.add_seq('/type/work', '/works/OL%dW')
    schema.add_seq('/type/publisher', '/publishers/OL%dP')

    _sql = schema.sql

    # custom postgres functions required by OL.
    more_sql = """
    CREATE OR REPLACE FUNCTION get_olid(text) RETURNS text AS $$
        select regexp_replace($1, '.*(OL[0-9]+[A-Z])', E'\\1') where $1 ~ '^/.*/OL[0-9]+[A-Z]$';
    $$ LANGUAGE SQL IMMUTABLE;

    CREATE INDEX thing_olid_idx ON thing(get_olid(key));

    CREATE TABLE likes (
        username text NOT NULL,
        work_id integer NOT NULL,
        weight integer,
        edition_id integer default null,
        updated timestamp without time zone default (current_timestamp at time zone 'utc'),
        created timestamp without time zone default (current_timestamp at time zone 'utc'),
        primary key (username, work_id)
    );

    CREATE TABLE ratings (
        username text NOT NULL,
        work_id integer NOT NULL,
        rating integer,
        edition_id integer default null,
        updated timestamp without time zone default (current_timestamp at time zone 'utc'),
        created timestamp without time zone default (current_timestamp at time zone 'utc'),
        primary key (username, work_id)
    );

    CREATE TABLE bookshelves_books (
        username text NOT NULL,
        work_id integer NOT NULL,
        bookshelf_id INTEGER references bookshelves(id) ON DELETE CASCADE ON UPDATE CASCADE,
        edition_id integer default null,
        updated timestamp without time zone default (current_timestamp at time zone 'utc'),
        created timestamp without time zone default (current_timestamp at time zone 'utc'),
        primary key (username, work_id, bookshelf_id)
    );

    CREATE TABLE bookshelves (
        id serial not null primary key,
        name text,
        description text default null,
        archived BOOLEAN DEFAULT FALSE,
        updated timestamp without time zone default (current_timestamp at time zone 'utc'),
        created timestamp without time zone default (current_timestamp at time zone 'utc')
    );

    CREATE TABLE bookshelves_votes (
        username text NOT NULL,
        bookshelf_id serial NOT NULL REFERENCES bookshelves(id) ON DELETE CASCADE ON UPDATE CASCADE,
        updated timestamp without time zone default (current_timestamp at time zone 'utc'),
        created timestamp without time zone default (current_timestamp at time zone 'utc'),
        primary key (username, bookshelf_id)
    );

    CREATE TABLE stats (
        id serial primary key,
        key text unique,
        type text,
        created timestamp without time zone,
        updated timestamp without time zone,
        json text
    );
    CREATE INDEX stats_type_idx ON stats(type);
    CREATE INDEX stats_created_idx ON stats(created);
    CREATE INDEX stats_updated_idx ON stats(updated);

    CREATE TABLE waitingloan (
        id serial primary key,
        book_key text,
        user_key text,
        status text default 'waiting',
        position integer,
        wl_size integer,
        since timestamp without time zone default (current_timestamp at time zone 'utc'),
        last_update timestamp without time zone default (current_timestamp at time zone 'utc'),
        expiry timestamp without time zone,
        available_email_sent boolean default 'f',
        UNIQUE (book_key, user_key)
    );

    CREATE INDEX waitingloan_user_key_idx ON waitingloan(user_key);
    CREATE INDEX waitingloan_status_idx ON waitingloan(status);


    CREATE TABLE import_batch (
        id serial primary key,
        name text,
        submitter text,
        submit_time timestamp without time zone default (current_timestamp at time zone 'utc')
    );

    CREATE INDEX import_batch_name ON import_batch(name);
    CREATE INDEX import_batch_submitter_idx ON import_batch(submitter);
    CREATE INDEX import_batch_submit_time_idx ON import_batch(submit_time);

    CREATE TABLE import_item (
        id serial primary key,
        batch_id integer references import_batch,
        added_time timestamp without time zone default (current_timestamp at time zone 'utc'),
        import_time timestamp without time zone,
        status text default 'pending',
        error text,
        ia_id text,
        ol_key text,
        comments text,
        UNIQUE (batch_id, ia_id)
    );
    CREATE INDEX import_item_batch_id ON import_item(batch_id);
    CREATE INDEX import_item_import_time ON import_item(import_time);
    CREATE INDEX import_item_status ON import_item(status);
    CREATE INDEX import_item_ia_id ON import_item(ia_id);
    """

    # monkey patch schema.sql to include the custom functions
    schema.sql = lambda: web.safestr(_sql()) + more_sql
    return schema

def register_schema():
    """Register the schema definied in this module as the default schema."""
    dbstore.default_schema = get_schema()

if __name__ == "__main__":
    print get_schema().sql()
