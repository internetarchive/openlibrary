
CREATE TABLE ratings (
    username text NOT NULL,
    work_id integer NOT NULL,
    rating integer,
    edition_id integer default null,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, work_id)
);

CREATE TABLE bookshelves (
    id serial not null primary key,
    name text,
    description text default null,
    archived BOOLEAN DEFAULT FALSE,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc')
);

CREATE TABLE bookshelves_books (
    username text NOT NULL,
    work_id integer NOT NULL,
    bookshelf_id INTEGER references bookshelves(id) ON DELETE CASCADE ON UPDATE CASCADE,
    edition_id integer default null,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, work_id, bookshelf_id)
);

CREATE TABLE bookshelves_votes (
    username text NOT NULL,
    bookshelf_id serial NOT NULL REFERENCES bookshelves(id) ON DELETE CASCADE ON UPDATE CASCADE,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, bookshelf_id)
);
