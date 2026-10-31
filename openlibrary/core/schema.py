"""Infobase schema for Open Library"""

import web

from infogami.infobase import dbstore


def get_schema():
    schema = dbstore.Schema()
    schema.add_table_group("type", "/type/type")
    schema.add_table_group("type", "/type/property")
    schema.add_table_group("type", "/type/backreference")
    schema.add_table_group("user", "/type/user")
    schema.add_table_group("user", "/type/usergroup")
    schema.add_table_group("user", "/type/permission")

    datatypes = ["str", "int", "ref", "boolean"]

    schema.add_table_group("edition", "/type/edition", datatypes)
    schema.add_table_group("author", "/type/author", datatypes)
    schema.add_table_group("scan", "/type/scan_location", datatypes)
    schema.add_table_group("scan", "/type/scan_record", datatypes)

    schema.add_table_group("work", "/type/work", datatypes)
    schema.add_table_group("publisher", "/type/publisher", datatypes)
    schema.add_table_group("subject", "/type/subject", datatypes)
    # schema.add_table_group('tag', '/type/tag', datatypes)

    schema.add_seq("/type/edition", "/books/OL%dM")
    schema.add_seq("/type/author", "/authors/OL%dA")
    # schema.add_seq('/type/list', '/lists/OL%dL')
    # schema.add_seq('/type/series', '/series/OL%dS')

    schema.add_seq("/type/work", "/works/OL%dW")
    schema.add_seq("/type/publisher", "/publishers/OL%dP")
    schema.add_seq("/type/tag", "/tags/OL%dT")

    _sql = schema.sql

    # custom postgres functions required by OL.
    more_sql = """
    CREATE OR REPLACE FUNCTION get_olid(text) RETURNS text AS $$
        select regexp_replace($1, '.*(OL[0-9]+[A-Z])', E'\\1') where $1 ~ '^/.*/OL[0-9]+[A-Z]$';
    $$ LANGUAGE SQL IMMUTABLE;

    CREATE INDEX thing_olid_idx ON thing(get_olid(key));

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
        data text,
        ol_key text,
        comments text,
        submitter text,
        UNIQUE (batch_id, ia_id)
    );
    CREATE INDEX import_item_batch_id ON import_item(batch_id);
    CREATE INDEX import_item_import_time ON import_item(import_time);
    CREATE INDEX import_item_status ON import_item(status);
    CREATE INDEX import_item_ia_id ON import_item(ia_id);

    CREATE TABLE solr_updater_queue (
        id bigserial primary key,
        transaction_id int references transaction,
        keys jsonb,
        created timestamp without time zone default (current_timestamp at time zone 'utc'),
        CHECK ((transaction_id IS NULL) <> (keys IS NULL))
    );

    CREATE FUNCTION queue_solr_transaction() RETURNS trigger AS $$
    BEGIN
        INSERT INTO public.solr_updater_queue (transaction_id) VALUES (NEW.id);
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER transaction_solr_update_queue
        AFTER INSERT ON transaction
        FOR EACH ROW EXECUTE FUNCTION queue_solr_transaction();

    CREATE FUNCTION queue_solr_force_update() RETURNS trigger AS $$
    BEGIN
        IF NEW.key = 'solr-force-update' THEN
            INSERT INTO public.solr_updater_queue (keys)
            VALUES (COALESCE(NEW.json::jsonb -> 'keys', '[]'::jsonb));
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER store_solr_force_update_queue
        AFTER INSERT OR UPDATE ON store
        FOR EACH ROW EXECUTE FUNCTION queue_solr_force_update();
    """

    # monkey patch schema.sql to include the custom functions
    schema.sql = lambda: web.safestr(_sql()) + more_sql
    return schema


def register_schema():
    """Register the schema defined in this module as the default schema."""
    dbstore.default_schema = get_schema()


if __name__ == "__main__":
    print(get_schema().sql())
