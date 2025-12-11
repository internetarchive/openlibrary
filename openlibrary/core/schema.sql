
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
CREATE INDEX bookshelves_books_updated_idx ON bookshelves_books (updated);
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

-- Multi-index optimized to fetch a specific user's check-ins
CREATE INDEX bookshelves_events_user_checkins_idx
    ON bookshelves_events (username, work_id, event_type DESC, event_date DESC);

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
);

CREATE TABLE bestbooks (
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

CREATE INDEX bestbooks_username ON bestbooks (username);
CREATE INDEX bestbooks_work ON bestbooks (work_id);
CREATE INDEX bestbooks_topic ON bestbooks (topic);

-- Solr Update Retry Queue (Issue #10737)
CREATE TABLE solr_update_failures (
    id serial PRIMARY KEY,
    keys TEXT[] NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    error_type VARCHAR(100) NOT NULL,
    error_message TEXT,
    stack_trace TEXT,
    solr_response_code INT,
    retry_count INT DEFAULT 0 NOT NULL,
    max_retries INT DEFAULT 10 NOT NULL,
    next_retry_at timestamp without time zone NOT NULL,
    first_failed_at timestamp without time zone DEFAULT (current_timestamp at time zone 'utc') NOT NULL,
    last_attempted_at timestamp without time zone DEFAULT (current_timestamp at time zone 'utc') NOT NULL,
    batch_metadata JSONB,
    CONSTRAINT retry_count_positive CHECK (retry_count >= 0),
    CONSTRAINT max_retries_positive CHECK (max_retries > 0),
    CONSTRAINT keys_not_empty CHECK (array_length(keys, 1) > 0)
);

CREATE INDEX idx_solr_failures_retry ON solr_update_failures(next_retry_at, retry_count) 
WHERE retry_count < max_retries;
CREATE INDEX idx_solr_failures_oldest ON solr_update_failures(first_failed_at DESC);
CREATE INDEX idx_solr_failures_entity ON solr_update_failures(entity_type);
CREATE INDEX idx_solr_failures_error_type ON solr_update_failures(error_type);

CREATE TABLE solr_update_failures_archived (
    id INT NOT NULL,
    keys TEXT[] NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    error_type VARCHAR(100) NOT NULL,
    error_message TEXT,
    stack_trace TEXT,
    solr_response_code INT,
    retry_count INT NOT NULL,
    max_retries INT NOT NULL,
    next_retry_at timestamp without time zone NOT NULL,
    first_failed_at timestamp without time zone NOT NULL,
    last_attempted_at timestamp without time zone NOT NULL,
    batch_metadata JSONB,
    archived_at timestamp without time zone DEFAULT (current_timestamp at time zone 'utc') NOT NULL,
    archived_reason VARCHAR(255) DEFAULT 'max_retries_exceeded' NOT NULL,
    manual_resolution_notes TEXT,
    resolved_at timestamp without time zone,
    resolved_by VARCHAR(255),
    PRIMARY KEY (id, archived_at)
);

CREATE INDEX idx_solr_failures_archived_unresolved ON solr_update_failures_archived(archived_at DESC) 
WHERE resolved_at IS NULL;
