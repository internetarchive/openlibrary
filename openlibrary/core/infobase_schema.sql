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
    created timestamp default (current_timestamp at time zone 'utc'),
    last_modified timestamp default (current_timestamp at time zone 'utc')
);
create index thing_type_idx on thing (type);

create index thing_latest_revision_idx on thing (latest_revision);

create index thing_last_modified_idx on thing (last_modified);

create index thing_created_idx on thing (created);

create unique index thing_key_idx on thing (key);

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

create index transaction_author_id_idx on transaction (author_id);

create index transaction_ip_idx on transaction (ip);

create index transaction_created_idx on transaction (created);

create table transaction_index (
    tx_id int references transaction,
    key text,
    value text
);

create index transaction_index_key_value_idx on transaction_index (key, value);
create index transaction_index_tx_id_idx on transaction_index (tx_id);

create table version (
    id serial primary key,
    thing_id int references thing,
    revision int,
    transaction_id int references transaction,
    unique (thing_id, revision)
);

create table property (
    id serial primary key,
    type int references thing,
    name text,
    unique (type, name)
);

create function get_property_name(integer, integer)
returns text as
'select property.name FROM property, thing WHERE thing.type = property.type AND thing.id=$1 AND property.id=$2;'
language sql;

create table account (
    thing_id int references thing,
    email text,
    password text,
    active boolean default 't',
    bot boolean default 'f',
    verified boolean default 'f',

    unique (email)
);

create index account_thing_id_idx on account (thing_id);
create index account_thing_email_idx on account (email);
create index account_thing_active_idx on account (active);
create index account_thing_bot_idx on account (bot);

create table data (
    thing_id int references thing,
    revision int,
    data text
);
create unique index data_thing_id_revision_idx on data (thing_id, revision);


create table author_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index author_boolean_idx on author_boolean (key_id, value);
create index author_boolean_thing_id_idx on author_boolean (thing_id);

create table author_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index author_int_idx on author_int (key_id, value);
create index author_int_thing_id_idx on author_int (thing_id);

create table author_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index author_ref_idx on author_ref (key_id, value);
create index author_ref_thing_id_idx on author_ref (thing_id);

create table author_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index author_str_idx on author_str (key_id, value);
create index author_str_thing_id_idx on author_str (thing_id);

create table datum_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index datum_int_idx on datum_int (key_id, value);
create index datum_int_thing_id_idx on datum_int (thing_id);

create table datum_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index datum_ref_idx on datum_ref (key_id, value);
create index datum_ref_thing_id_idx on datum_ref (thing_id);

create table datum_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index datum_str_idx on datum_str (key_id, value);
create index datum_str_thing_id_idx on datum_str (thing_id);

create table edition_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index edition_boolean_idx on edition_boolean (key_id, value);
create index edition_boolean_thing_id_idx on edition_boolean (thing_id);

create table edition_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index edition_int_idx on edition_int (key_id, value);
create index edition_int_thing_id_idx on edition_int (thing_id);

create table edition_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index edition_ref_idx on edition_ref (key_id, value);
create index edition_ref_thing_id_idx on edition_ref (thing_id);

create table edition_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index edition_str_idx on edition_str (key_id, value);
create index edition_str_thing_id_idx on edition_str (thing_id);

create table publisher_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index publisher_boolean_idx on publisher_boolean (key_id, value);
create index publisher_boolean_thing_id_idx on publisher_boolean (thing_id);

create table publisher_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index publisher_int_idx on publisher_int (key_id, value);
create index publisher_int_thing_id_idx on publisher_int (thing_id);

create table publisher_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index publisher_ref_idx on publisher_ref (key_id, value);
create index publisher_ref_thing_id_idx on publisher_ref (thing_id);

create table publisher_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index publisher_str_idx on publisher_str (key_id, value);
create index publisher_str_thing_id_idx on publisher_str (thing_id);

create table scan_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index scan_boolean_idx on scan_boolean (key_id, value);
create index scan_boolean_thing_id_idx on scan_boolean (thing_id);

create table scan_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index scan_int_idx on scan_int (key_id, value);
create index scan_int_thing_id_idx on scan_int (thing_id);

create table scan_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index scan_ref_idx on scan_ref (key_id, value);
create index scan_ref_thing_id_idx on scan_ref (thing_id);

create table scan_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index scan_str_idx on scan_str (key_id, value);
create index scan_str_thing_id_idx on scan_str (thing_id);

create table subject_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index subject_boolean_idx on subject_boolean (key_id, value);
create index subject_boolean_thing_id_idx on subject_boolean (thing_id);

create table subject_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index subject_int_idx on subject_int (key_id, value);
create index subject_int_thing_id_idx on subject_int (thing_id);

create table subject_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index subject_ref_idx on subject_ref (key_id, value);
create index subject_ref_thing_id_idx on subject_ref (thing_id);

create table subject_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index subject_str_idx on subject_str (key_id, value);
create index subject_str_thing_id_idx on subject_str (thing_id);

create table type_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index type_int_idx on type_int (key_id, value);
create index type_int_thing_id_idx on type_int (thing_id);

create table type_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index type_ref_idx on type_ref (key_id, value);
create index type_ref_thing_id_idx on type_ref (thing_id);

create table type_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index type_str_idx on type_str (key_id, value);
create index type_str_thing_id_idx on type_str (thing_id);

create table user_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index user_int_idx on user_int (key_id, value);
create index user_int_thing_id_idx on user_int (thing_id);

create table user_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index user_ref_idx on user_ref (key_id, value);
create index user_ref_thing_id_idx on user_ref (thing_id);

create table user_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index user_str_idx on user_str (key_id, value);
create index user_str_thing_id_idx on user_str (thing_id);

create table work_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index work_boolean_idx on work_boolean (key_id, value);
create index work_boolean_thing_id_idx on work_boolean (thing_id);

create table work_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index work_int_idx on work_int (key_id, value);
create index work_int_thing_id_idx on work_int (thing_id);

create table work_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index work_ref_idx on work_ref (key_id, value);
create index work_ref_thing_id_idx on work_ref (thing_id);

create table work_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index work_str_idx on work_str (key_id, value);
create index work_str_thing_id_idx on work_str (thing_id);

create table tag_boolean (
    thing_id int references thing,
    key_id int references property,
    value boolean,
    ordering int default NULL
);
create index tag_boolean_idx on tag_boolean (key_id, value);
create index tag_boolean_thing_id_idx on tag_boolean (thing_id);

create table tag_int (
    thing_id int references thing,
    key_id int references property,
    value int,
    ordering int default NULL
);
create index tag_int_idx on tag_int (key_id, value);
create index tag_int_thing_id_idx on tag_int (thing_id);

create table tag_ref (
    thing_id int references thing,
    key_id int references property,
    value int references thing,
    ordering int default NULL
);
create index tag_ref_idx on tag_ref (key_id, value);
create index tag_ref_thing_id_idx on tag_ref (thing_id);

create table tag_str (
    thing_id int references thing,
    key_id int references property,
    value varchar(2048),
    ordering int default NULL
);
create index tag_str_idx on tag_str (key_id, value);
create index tag_str_thing_id_idx on tag_str (thing_id);

-- sequences --
create sequence type_edition_seq;

create sequence type_author_seq;

create sequence type_work_seq;

create sequence type_publisher_seq;

create sequence type_tag_seq;

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

create index store_index_store_id_idx on store_index (store_id);
create index store_idx on store_index (type, name, value);

create table seq (
    id serial primary key,
    name text unique,
    value int default 0
);

commit;

/* SQL found in /openlibrary/core/schema.py#get_schema() `more_sql` variable: */

create or replace function get_olid(text) returns text as $$
    select regexp_replace($1, '.*(OL[0-9]+[A-Z])', E'\1') where $1 ~ '^/.*/OL[0-9]+[A-Z]$';
$$ language sql immutable;

create index thing_olid_idx on thing (get_olid(key));

create table stats (
    id serial primary key,
    key text unique,
    type text,
    created timestamp without time zone,
    updated timestamp without time zone,
    json text
);
create index stats_type_idx on stats (type);
create index stats_created_idx on stats (created);
create index stats_updated_idx on stats (updated);

create table waitingloan (
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
    unique (book_key, user_key)
);

create index waitingloan_user_key_idx on waitingloan (user_key);
create index waitingloan_status_idx on waitingloan (status);


create table import_batch (
    id serial primary key,
    name text,
    submitter text,
    submit_time timestamp without time zone default (current_timestamp at time zone 'utc')
);

create index import_batch_name on import_batch (name);
create index import_batch_submitter_idx on import_batch (submitter);
create index import_batch_submit_time_idx on import_batch (submit_time);

create table import_item (
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
    unique (batch_id, ia_id)
);
create index import_item_batch_id on import_item (batch_id);
create index import_item_import_time on import_item (import_time);
create index import_item_status on import_item (status);
create index import_item_status_id on import_item (status, id);
create index import_item_submitter on import_item (submitter);
create index import_item_ia_id on import_item (ia_id);
