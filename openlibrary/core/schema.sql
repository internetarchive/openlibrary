
CREATE TABLE ratings (
    username text NOT NULL,
    work_id integer NOT NULL,
    rating integer,
    edition_id integer default null,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, work_id)
);
CREATE INDEX ratings_work_id_idx ON ratings (work_id);

CREATE TABLE follows (
    subscriber text NOT NULL,
    publisher text NOT NULL,
    disabled BOOLEAN DEFAULT FALSE,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (subscriber, publisher)
);
CREATE INDEX subscriber_idx ON follows (subscriber);
CREATE INDEX publisher_idx ON follows (publisher);

CREATE TABLE booknotes (
    username text NOT NULL,
    work_id integer NOT NULL,
    edition_id integer NOT NULL default -1,
    notes text NOT NULL,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, work_id, edition_id)
);
CREATE INDEX booknotes_work_id_idx ON booknotes (work_id);

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
CREATE INDEX bookshelves_books_work_id_idx ON bookshelves_books (work_id);

INSERT INTO bookshelves (name, description) VALUES ('Want to Read', 'A list of books I want to read');
INSERT INTO bookshelves (name, description) VALUES ('Currently Reading', 'A list of books I am currently reading');
INSERT INTO bookshelves (name, description) VALUES ('Already Read', 'A list of books I have finished reading');

CREATE TABLE bookshelves_events (
    id serial primary key,
    username text not null,
    work_id integer not null,
    edition_id integer not null,
    event_type integer not null,
    event_date text not null,
    data json,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc')
);

CREATE TABLE observations (
    work_id INTEGER not null,
    edition_id INTEGER default -1,
    username text not null,
    observation_type INTEGER not null,
    observation_value INTEGER not null,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (work_id, edition_id, username, observation_value, observation_type)
);
CREATE INDEX observations_username_idx ON observations (username);

CREATE TABLE community_edits_queue (
    id serial not null primary key,
    title text,
    submitter text not null,
    reviewer text default null,
    url text not null,
    mr_type int not null default 1,
    status int not null default 1,
    comments json,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    updated timestamp without time zone default (current_timestamp at time zone 'utc')
);

CREATE TABLE yearly_reading_goals (
    username text not null,
    year integer not null,
    target integer not null,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, year)
);

CREATE TABLE wikidata (
    id text not null primary key,
    data json,
    updated timestamp without time zone default (current_timestamp at time zone 'utc')
)
