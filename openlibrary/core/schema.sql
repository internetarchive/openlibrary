CREATE TABLE IF NOT EXISTS ratings (
    username text NOT NULL,
    work_id integer NOT NULL,
    rating integer,
    edition_id integer default null,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, work_id)
);
CREATE INDEX IF NOT EXISTS ratings_work_id_idx ON ratings (work_id);

CREATE TABLE IF NOT EXISTS follows (
    subscriber text NOT NULL,
    publisher text NOT NULL,
    disabled BOOLEAN DEFAULT FALSE,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (subscriber, publisher)
);
CREATE TABLE IF NOT EXISTS likes (
    username    TEXT        NOT NULL,
    key         TEXT        NOT NULL,   -- full infogami key, e.g. /works/OL123W
    value       SMALLINT    NOT NULL DEFAULT 1 CHECK (value IN (1, -1)),
    created     TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (username, key)
);
CREATE INDEX IF NOT EXISTS likes_key_idx      ON likes (key);
CREATE INDEX IF NOT EXISTS likes_username_idx ON likes (username);

CREATE INDEX IF NOT EXISTS subscriber_idx ON follows (subscriber);
CREATE INDEX IF NOT EXISTS publisher_idx ON follows (publisher);

CREATE TABLE IF NOT EXISTS booknotes (
    username text NOT NULL,
    work_id integer NOT NULL,
    edition_id integer NOT NULL default -1,
    notes text NOT NULL,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, work_id, edition_id)
);
CREATE INDEX IF NOT EXISTS booknotes_work_id_idx ON booknotes (work_id);

CREATE TABLE IF NOT EXISTS bookshelves (
    id serial not null primary key,
    name text,
    description text default null,
    archived BOOLEAN DEFAULT FALSE,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc')
);

CREATE TABLE IF NOT EXISTS bookshelves_books (
    username text NOT NULL,
    work_id integer NOT NULL,
    bookshelf_id INTEGER references bookshelves(id) ON DELETE CASCADE ON UPDATE CASCADE,
    edition_id integer default null,
    private BOOLEAN,
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, work_id, bookshelf_id)
);
CREATE INDEX IF NOT EXISTS bookshelves_books_work_id_idx ON bookshelves_books (work_id);
CREATE INDEX IF NOT EXISTS bookshelves_books_updated_idx ON bookshelves_books (updated);
CREATE INDEX IF NOT EXISTS bookshelves_books_created_idx ON bookshelves_books (created);
-- No UNIQUE constraint exists on bookshelves.name, so these use a
-- WHERE NOT EXISTS guard (rather than ON CONFLICT) to stay idempotent when
-- schema.sql is re-applied against an already-provisioned dev database.
INSERT INTO bookshelves (name, description)
    SELECT
        'Want to Read',
        'A list of books I want to read'
    WHERE NOT EXISTS (
        SELECT 1 FROM bookshelves
        WHERE name = 'Want to Read'
    );
INSERT INTO bookshelves (name, description)
    SELECT
        'Currently Reading',
        'A list of books I am currently reading'
    WHERE NOT EXISTS (
        SELECT 1 FROM bookshelves
        WHERE name = 'Currently Reading'
    );
INSERT INTO bookshelves (name, description)
    SELECT
        'Already Read',
        'A list of books I have finished reading'
    WHERE NOT EXISTS (
        SELECT 1 FROM bookshelves
        WHERE name = 'Already Read'
    );
INSERT INTO bookshelves (name, description)
    SELECT
        'Stopped Reading',
        'A list of books I have stopped reading'
    WHERE NOT EXISTS (
        SELECT 1 FROM bookshelves
        WHERE name = 'Stopped Reading'
    );

CREATE TABLE IF NOT EXISTS bookshelves_events (
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

-- Multi-index optimized to fetch a specific user's check-ins
CREATE INDEX IF NOT EXISTS bookshelves_events_user_checkins_idx
    ON bookshelves_events (username, work_id, event_type DESC, event_date DESC);

CREATE TABLE IF NOT EXISTS observations (
    work_id INTEGER not null,
    edition_id INTEGER default -1,
    username text not null,
    observation_type INTEGER not null,
    observation_value INTEGER not null,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (work_id, edition_id, username, observation_value, observation_type)
);
CREATE INDEX IF NOT EXISTS observations_username_idx ON observations (username);

CREATE TABLE IF NOT EXISTS community_edits_queue (
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

CREATE INDEX IF NOT EXISTS community_edits_queue_updated_idx ON community_edits_queue (updated);

CREATE TABLE IF NOT EXISTS yearly_reading_goals (
    username text not null,
    year integer not null,
    target integer not null,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (username, year)
);

CREATE TABLE IF NOT EXISTS wikidata (
    id text not null primary key,
    data json,
    updated timestamp without time zone default (current_timestamp at time zone 'utc')
);

CREATE TABLE IF NOT EXISTS bestbooks (
    award_id serial not null primary key,
    username text not null,
    work_id integer not null,
    edition_id integer default null,
    topic text not null,
    comment text not null,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    UNIQUE (username, work_id),
    UNIQUE (username, topic)
);

CREATE INDEX IF NOT EXISTS bestbooks_username ON bestbooks (username);
CREATE INDEX IF NOT EXISTS bestbooks_work ON bestbooks (work_id);
CREATE INDEX IF NOT EXISTS bestbooks_topic ON bestbooks (topic);

CREATE TABLE IF NOT EXISTS acquisitions (
    id serial primary key,
    work_id integer not null,
    edition_id integer not null,
    provider_name text not null,
    local_id text not null,
    -- provider metadata blob: prices, formats, urls, etc.
    data jsonb not null,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    UNIQUE (local_id, provider_name)
);

CREATE INDEX IF NOT EXISTS acquisitions_work_id_idx ON acquisitions (work_id);
CREATE INDEX IF NOT EXISTS acquisitions_edition_id_idx ON acquisitions (edition_id);
CREATE INDEX IF NOT EXISTS acquisitions_updated_idx ON acquisitions (updated);
