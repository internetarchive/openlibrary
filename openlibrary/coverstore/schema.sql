
create table category (
    id serial primary key,
    name text
);

create table cover (
    id serial primary key,
    category_id int references category,
    olid text,
    filename text,
    filename_s text,
    filename_m text,
    filename_l text,
    author text,
    ip inet,
    source_url text,
    source text,
    isbn text,
    width int,
    height int,
    archived boolean,
    deleted boolean default false,
    created timestamp default(current_timestamp at time zone 'utc'),
    last_modified timestamp default(current_timestamp at time zone 'utc')
);

create index cover_olid_idx ON cover (olid);
create index cover_last_modified_idx ON cover (last_modified);
create index cover_created_idx ON cover (created);
create index cover_deleted_idx ON cover(deleted);
create index cover_archived_idx ON cover(archived);

create table log (
    id serial primary key,
    cover_id int references cover(id),
    action text,
    timestamp timestamp
);

create index log_timestamp_idx on log(timestamp);

