create table files (
    id serial,
    ia char(32),
    part char(32)
);

create table rec (
    id serial,
    marc_file integer,
    pos integer,
    len integer,
    title char(25),
    lccn char(32),
    call_number char(32)
);
    
create table isbn (
    value char(16),
    rec integer
);

create table oclc (
    value char(32),
    rec integer
);
