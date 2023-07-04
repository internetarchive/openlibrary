/*
 * Infobase database schema
 *
 * This SQL (including "--" style comments) is returned by get_schema() in /openlibrary/core/schema.py
 *
 * This file, along with /infogami/infobase/bootstrap.py may be quite useful during disaster recovery
 * events.
 */

-- changelog:
-- 10: added active and bot columns to account and created meta table to track the schema version.

create table meta (
    version int
);
insert into meta (version) values (10);

create table thing (
    id serial primary key,
    key text,
    type int references thing,
    latest_revision int default 1,
    created timestamp default(current_timestamp at time zone 'utc'),
    last_modified timestamp default(current_timestamp at time zone 'utc')
);
create index thing_type_idx ON thing(type);

create index thing_latest_revision_idx ON thing(latest_revision);

create index thing_last_modified_idx ON thing(last_modified);

create index thing_created_idx ON thing(created);

create unique index thing_key_idx ON thing(key);

create table transaction (
    id serial primary key,
    action varchar(256),
    author_id int references thing,
    ip inet,
    comment text,
    bot boolean default 'f', -- true if the change is made by a bot
    created timestamp default (current_timestamp at time zone 'utc'),
    changes text,
    data text
);

create index transaction_author_id_idx ON transaction(author_id);

create index transaction_ip_idx ON transaction(ip);

create index transaction_created_idx ON transaction(created);

create table transaction_index (
    tx_id int references transaction,
    key text,
    value text
);

create index transaction_index_key_value_idx ON transaction_index(key, value);
create index transaction_index_tx_id_idx ON transaction_index(tx_id);

create table version (
    id serial primary key,
    thing_id int references thing,
    revision int,
    transaction_id int references transaction,
    UNIQUE (thing_id, revision)
);

create table property (
    id serial primary key,
    type int references thing,
    name text,
    UNIQUE (type, name)
);

CREATE FUNCTION get_property_name(integer, integer)
RETURNS text AS
'select property.name FROM property, thing WHERE thing.type = property.type AND thing.id=$1 AND property.id=$2;'
LANGUAGE SQL;

create table account (
    thing_id int references thing,
    email text,
    password text,
    active boolean default 't',
    bot  boolean default 'f',
    verified boolean default 'f',

    UNIQUE(email)
);

create index account_thing_id_idx ON account(thing_id);
create index account_thing_email_idx ON account(email);
create index account_thing_active_idx ON account(active);
create index account_thing_bot_idx ON account(bot);

create table data (
    thing_id int references thing,
    revision int,
    data text
);
create unique index data_thing_id_revision_idx ON data(thing_id, revision);


create table author_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index author_boolean_idx ON author_boolean(key_id, value);
create index author_boolean_thing_id_idx ON author_boolean(thing_id);

create table author_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index author_int_idx ON author_int(key_id, value);
create index author_int_thing_id_idx ON author_int(thing_id);

create table author_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index author_ref_idx ON author_ref(key_id, value);
create index author_ref_thing_id_idx ON author_ref(thing_id);

create table author_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index author_str_idx ON author_str(key_id, value);
create index author_str_thing_id_idx ON author_str(thing_id);

create table datum_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index datum_int_idx ON datum_int(key_id, value);
create index datum_int_thing_id_idx ON datum_int(thing_id);

create table datum_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index datum_ref_idx ON datum_ref(key_id, value);
create index datum_ref_thing_id_idx ON datum_ref(thing_id);

create table datum_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index datum_str_idx ON datum_str(key_id, value);
create index datum_str_thing_id_idx ON datum_str(thing_id);

create table edition_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index edition_boolean_idx ON edition_boolean(key_id, value);
create index edition_boolean_thing_id_idx ON edition_boolean(thing_id);

create table edition_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index edition_int_idx ON edition_int(key_id, value);
create index edition_int_thing_id_idx ON edition_int(thing_id);

create table edition_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index edition_ref_idx ON edition_ref(key_id, value);
create index edition_ref_thing_id_idx ON edition_ref(thing_id);

create table edition_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index edition_str_idx ON edition_str(key_id, value);
create index edition_str_thing_id_idx ON edition_str(thing_id);

create table publisher_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index publisher_boolean_idx ON publisher_boolean(key_id, value);
create index publisher_boolean_thing_id_idx ON publisher_boolean(thing_id);

create table publisher_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index publisher_int_idx ON publisher_int(key_id, value);
create index publisher_int_thing_id_idx ON publisher_int(thing_id);

create table publisher_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index publisher_ref_idx ON publisher_ref(key_id, value);
create index publisher_ref_thing_id_idx ON publisher_ref(thing_id);

create table publisher_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index publisher_str_idx ON publisher_str(key_id, value);
create index publisher_str_thing_id_idx ON publisher_str(thing_id);

create table scan_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index scan_boolean_idx ON scan_boolean(key_id, value);
create index scan_boolean_thing_id_idx ON scan_boolean(thing_id);

create table scan_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index scan_int_idx ON scan_int(key_id, value);
create index scan_int_thing_id_idx ON scan_int(thing_id);

create table scan_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index scan_ref_idx ON scan_ref(key_id, value);
create index scan_ref_thing_id_idx ON scan_ref(thing_id);

create table scan_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index scan_str_idx ON scan_str(key_id, value);
create index scan_str_thing_id_idx ON scan_str(thing_id);

create table subject_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index subject_boolean_idx ON subject_boolean(key_id, value);
create index subject_boolean_thing_id_idx ON subject_boolean(thing_id);

create table subject_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index subject_int_idx ON subject_int(key_id, value);
create index subject_int_thing_id_idx ON subject_int(thing_id);

create table subject_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index subject_ref_idx ON subject_ref(key_id, value);
create index subject_ref_thing_id_idx ON subject_ref(thing_id);

create table subject_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index subject_str_idx ON subject_str(key_id, value);
create index subject_str_thing_id_idx ON subject_str(thing_id);

create table type_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index type_int_idx ON type_int(key_id, value);
create index type_int_thing_id_idx ON type_int(thing_id);

create table type_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index type_ref_idx ON type_ref(key_id, value);
create index type_ref_thing_id_idx ON type_ref(thing_id);

create table type_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index type_str_idx ON type_str(key_id, value);
create index type_str_thing_id_idx ON type_str(thing_id);

create table user_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index user_int_idx ON user_int(key_id, value);
create index user_int_thing_id_idx ON user_int(thing_id);

create table user_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index user_ref_idx ON user_ref(key_id, value);
create index user_ref_thing_id_idx ON user_ref(thing_id);

create table user_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index user_str_idx ON user_str(key_id, value);
create index user_str_thing_id_idx ON user_str(thing_id);

create table work_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index work_boolean_idx ON work_boolean(key_id, value);
create index work_boolean_thing_id_idx ON work_boolean(thing_id);

create table work_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index work_int_idx ON work_int(key_id, value);
create index work_int_thing_id_idx ON work_int(thing_id);

create table work_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index work_ref_idx ON work_ref(key_id, value);
create index work_ref_thing_id_idx ON work_ref(thing_id);

create table work_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index work_str_idx ON work_str(key_id, value);
create index work_str_thing_id_idx ON work_str(thing_id);

create table tag_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index tag_boolean_idx ON tag_boolean(key_id, value);
create index tag_boolean_thing_id_idx ON tag_boolean(thing_id);

create table tag_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index tag_int_idx ON tag_int(key_id, value);
create index tag_int_thing_id_idx ON tag_int(thing_id);

create table tag_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index tag_ref_idx ON tag_ref(key_id, value);
create index tag_ref_thing_id_idx ON tag_ref(thing_id);

create table tag_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index tag_str_idx ON tag_str(key_id, value);
create index tag_str_thing_id_idx ON tag_str(thing_id);

-- sequences --
CREATE SEQUENCE type_edition_seq;

CREATE SEQUENCE type_author_seq;

CREATE SEQUENCE type_work_seq;

CREATE SEQUENCE type_publisher_seq;

CREATE SEQUENCE type_tag_seq;

create table store (
    id serial primary key,
    key text unique,
    json text
);

create table store_index (
    id serial primary key,
    store_id int references store,
    type text,
    name text,
    value text
);

create index store_index_store_id_idx ON store_index (store_id);
create index store_idx ON store_index(type, name, value);

create table seq (
    id serial primary key,
    name text unique,
    value int default 0
);

COMMIT;

/* SQL found in /openlibrary/core/schema.py#get_schema() `more_sql` variable: */

CREATE OR REPLACE FUNCTION get_olid(text) RETURNS text AS $$
    select regexp_replace($1, '.*(OL[0-9]+[A-Z])', E'\1') where $1 ~ '^/.*/OL[0-9]+[A-Z]$';
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
    UNIQUE (batch_id, ia_id)
);
CREATE INDEX import_item_batch_id ON import_item(batch_id);
CREATE INDEX import_item_import_time ON import_item(import_time);
CREATE INDEX import_item_status ON import_item(status);
CREATE INDEX import_item_ia_id ON import_item(ia_id);
