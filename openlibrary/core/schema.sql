
CREATE TABLE ratings (
    username text NOT NULL,
    work_id integer NOT NULL,
    rating integer,
    edition_id integer default null,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, work_id)
);

CREATE TABLE booknotes (
    username text NOT NULL,
    work_id integer NOT NULL,
    edition_id integer NOT NULL default -1,
    notes text NOT NULL,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, work_id, edition_id)
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
    private BOOLEAN,
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

INSERT INTO bookshelves (name, description) VALUES ('Want to Read', 'A list of books I want to read');
INSERT INTO bookshelves (name, description) VALUES ('Currently Reading', 'A list of books I am currently reading');
INSERT INTO bookshelves (name, description) VALUES ('Already Read', 'A list of books I have finished reading');


CREATE TABLE observations (
    work_id INTEGER not null,
    edition_id INTEGER default -1,
    username text not null,
    observation_type INTEGER not null,
    observation_value INTEGER not null,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (work_id, edition_id, username, observation_value, observation_type)
);
