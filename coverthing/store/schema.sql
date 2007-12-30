create table thing (
    id serial primary key,
    created timestamp default (current_timestamp at time zone 'utc'),
    dummy int
);

create table datum (
    thing_id int references thing,
    key text,
    value text, 
    datatype int
);

CREATE INDEX datum_key_val_idx ON datum (key, value);
