alter table isbn add primary key (key, value);
create index isbn_index on isbn (value);
alter table oclc add primary key (key, value);
create index oclc_index on oclc (value);
alter table title add primary key (key, value);
create index title_index on title (value);
alter table lccn add primary key (key, value);
create index lccn_index on lccn (value);
