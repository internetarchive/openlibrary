CREATE TABLE ratings (
    username text NOT NULL,
    work_id integer NOT NULL,
    rating integer,
    edition_id integer DEFAULT null,
    updated timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    created timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    PRIMARY KEY (username, work_id)
);
CREATE INDEX ratings_work_id_idx ON ratings (work_id);

CREATE TABLE follows (
    subscriber text NOT NULL,
    publisher text NOT NULL,
    disabled boolean DEFAULT false,
    updated timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    created timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    PRIMARY KEY (subscriber, publisher)
);
CREATE INDEX subscriber_idx ON follows (subscriber);
CREATE INDEX publisher_idx ON follows (publisher);

CREATE TABLE booknotes (
    username text NOT NULL,
    work_id integer NOT NULL,
    edition_id integer NOT NULL DEFAULT -1,
    notes text NOT NULL,
    updated timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    created timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    PRIMARY KEY (username, work_id, edition_id)
);
CREATE INDEX booknotes_work_id_idx ON booknotes (work_id);

CREATE TABLE bookshelves (
    id serial NOT NULL PRIMARY KEY,
    name text,
    description text DEFAULT null,
    archived boolean DEFAULT false,
    updated timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    created timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc')
);

CREATE TABLE bookshelves_books (
    username text NOT NULL,
    work_id integer NOT NULL,
    bookshelf_id integer REFERENCES bookshelves (id) ON DELETE CASCADE ON UPDATE CASCADE,
    edition_id integer DEFAULT null,
    private boolean,
    updated timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    created timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    PRIMARY KEY (username, work_id, bookshelf_id)
);
CREATE INDEX bookshelves_books_work_id_idx ON bookshelves_books (work_id);
CREATE INDEX bookshelves_books_updated_idx ON bookshelves_books (updated);
INSERT INTO bookshelves (name, description) VALUES ('Want to Read', 'A list of books I want to read');
INSERT INTO bookshelves (name, description) VALUES ('Currently Reading', 'A list of books I am currently reading');
INSERT INTO bookshelves (name, description) VALUES ('Already Read', 'A list of books I have finished reading');

CREATE TABLE bookshelves_events (
    id serial PRIMARY KEY,
    username text NOT NULL,
    work_id integer NOT NULL,
    edition_id integer NOT NULL,
    event_type integer NOT NULL,
    event_date text NOT NULL,
    data json,
    updated timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    created timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc')
);

-- Multi-index optimized to fetch a specific user's check-ins
CREATE INDEX bookshelves_events_user_checkins_idx
ON bookshelves_events (username, work_id, event_type DESC, event_date DESC);

CREATE TABLE observations (
    work_id integer NOT NULL,
    edition_id integer DEFAULT -1,
    username text NOT NULL,
    observation_type integer NOT NULL,
    observation_value integer NOT NULL,
    created timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    PRIMARY KEY (work_id, edition_id, username, observation_value, observation_type)
);
CREATE INDEX observations_username_idx ON observations (username);

CREATE TABLE community_edits_queue (
    id serial NOT NULL PRIMARY KEY,
    title text,
    submitter text NOT NULL,
    reviewer text DEFAULT null,
    url text NOT NULL,
    mr_type int NOT NULL DEFAULT 1,
    status int NOT NULL DEFAULT 1,
    comments json,
    created timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    updated timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc')
);

CREATE TABLE yearly_reading_goals (
    username text NOT NULL,
    year integer NOT NULL,
    target integer NOT NULL,
    created timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    updated timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    PRIMARY KEY (username, year)
);

CREATE TABLE wikidata (
    id text NOT NULL PRIMARY KEY,
    data json,
    updated timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc')
);

CREATE TABLE bestbooks (
    award_id serial NOT NULL PRIMARY KEY,
    username text NOT NULL,
    work_id integer NOT NULL,
    edition_id integer DEFAULT null,
    topic text NOT NULL,
    comment text NOT NULL,
    created timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    updated timestamp without time zone DEFAULT (current_timestamp AT TIME ZONE 'utc'),
    UNIQUE (username, work_id),
    UNIQUE (username, topic)
);

CREATE INDEX bestbooks_username ON bestbooks (username);
CREATE INDEX bestbooks_work ON bestbooks (work_id);
CREATE INDEX bestbooks_topic ON bestbooks (topic);
