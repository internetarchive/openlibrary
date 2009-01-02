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
    id serial not null primary key,
    archive_id varchar(100) not null unique,
    name varchar(100)
);

create table marc_file (
    marc_source integer references marc_source (id),
    filename varchar(100)
)
