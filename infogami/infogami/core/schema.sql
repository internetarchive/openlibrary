CREATE TABLE site (
  id serial primary key,
  url text
);

CREATE TABLE page (
  id serial primary key,
  site_id int references site,
  path text
);

CREATE TABLE version (
  id serial primary key,
  revision int,
  page_id int references page,
  author text,
  created timestamp default (current_timestamp at time zone 'utc')
);

CREATE TABLE datum (
  id serial primary key,
  version_id int references version,
  key text,
  value text
);

CREATE TABLE login (
  id serial primary key,
  name text unique,
  email text,
  password text
);
