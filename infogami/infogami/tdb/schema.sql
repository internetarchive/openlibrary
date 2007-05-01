CREATE TABLE thing (
  id serial primary key,
  parent_id int references thing,
  name varchar(4000),
  latest_revision int,
  unique(parent_id, name)
);

CREATE TABLE version (
  id serial primary key,
  revision int,
  thing_id int references thing,
  author_id int references thing,
  ip inet,
  comment text,
  created timestamp default (current_timestamp at time zone 'utc'),
  unique (thing_id, revision)
);

CREATE TABLE datum (
  version_id int references version,
  key text,
  value text,
  data_type int default 0, -- {0: 'string', 1: 'reference', 2: 'int', 3: 'float', 4: 'date'}
  ordering int default null
);
