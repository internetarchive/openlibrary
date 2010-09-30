create table files (
    id serial,
    part varchar(80)
);

create table recs (
    id serial,
    marc_file integer,
    pos bigint,
    len integer
);
    
create table isbn (
    rec integer,
    value varchar(16)
);

create table oclc (
    rec integer,
    value varchar(32)
);

create table title (
    rec integer,
    value varchar(25)
);

create table lccn (
    rec integer,
    value varchar(32)
);


