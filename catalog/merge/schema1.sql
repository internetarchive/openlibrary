create table isbn (
    key varchar(16) not null,
    value varchar(16) not null
);

create table oclc (
    key varchar(16) not null,
    value varchar(16) not null
);

create table title (
    key varchar(16) not null,
    value varchar(25) not null
);

create table lccn (
    key varchar(16) not null,
    value varchar(16) not null
);

create table marc_source (
    id serial not null,
    archive_id varchar(100) not null unique,
    name varchar(100)
);

create table marc_file (
    id serial not null,
    marc_source integer not null,
    filename varchar(100) not null
);

create table marc_rec (
    id serial not null,
    marc_file integer not null,
    pos bigint not null,
    len integer not null
);

create table marc_isbn (
    marc_rec integer not null,
    value varchar(16) not null
);

create table marc_oclc (
    marc_rec integer not null,
    value varchar(16) not null
);

create table marc_lccn (
    marc_rec integer not null,
    value varchar(16) not null
);

create table marc_title (
    marc_rec integer not null,
    value varchar(25) not null
);
