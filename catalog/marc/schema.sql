create table files (
    id serial primary key,
    ia char(32),
    part char(32)
);

create table rec (
    id serial primary key,
    marc_file integer references files(id),
    pos integer,
    len integer,
    title char(25),
    lccn char(32),
    call_number char(32)
);
    
create table isbn (
    value char(16),
    rec integer,
    primary key(value, rec)
);

create table oclc (
    value char(32),
    rec integer,
    primary key(value, rec)
);
