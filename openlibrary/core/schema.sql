
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
    edition_id integer default null,
    notes text NOT NULL,
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

INSERT INTO bookshelves (name, description) VALUES ('Want to Read', 'A list of books I want to read');
INSERT INTO bookshelves (name, description) VALUES ('Currently Reading', 'A list of books I am currently reading');
INSERT INTO bookshelves (name, description) VALUES ('Already Read', 'A list of books I have finished reading');


CREATE TABLE observation_types (
    id serial not null primary key,
    type text,
    description text,
    allow_multiple_values BOOLEAN,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    updated timestamp without time zone default (current_timestamp at time zone 'utc')
);

-- New next_value must be set before a row is deleted
CREATE TABLE observation_values (
    id serial not null primary key,
    value text,
    type INTEGER references observation_types(id) ON DELETE CASCADE ON UPDATE CASCADE,
    next_value INTEGER references observation_values(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    updated timestamp without time zone default (current_timestamp at time zone 'utc')
);

CREATE TABLE observations (
    work_id INTEGER not null,
    edition_id INTEGER default null,
    username text not null,
    observation_id INTEGER references observation_values(id) ON DELETE CASCADE ON UPDATE CASCADE,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    primary key (work_id, edition_id, username, observation_id)
);


INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('pace', 'What is the pace of this book?', false);

INSERT INTO observation_values(value, type, next_value)
values
	('slow', currval('observation_types_id_seq'), null),
	('medium', currval('observation_types_id_seq'), lastval()),
	('fast', currval('observation_types_id_seq'), lastval());

    
INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('enjoyability', 'How entertaining is this book?', false);

INSERT INTO observation_values(value, type, next_value)
values
	('not applicable', currval('observation_types_id_seq'), null),
	('very boring', currval('observation_types_id_seq'), lastval()),
	('boring', currval('observation_types_id_seq'), lastval()),
	('neither entertaining nor boring', currval('observation_types_id_seq'), lastval()),
	('entertaining', currval('observation_types_id_seq'), lastval()),
	('very entertaining', currval('observation_types_id_seq'), lastval());

	
INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('clarity', 'How clearly is this book written?', false);

INSERT INTO observation_values(value, type, next_value)
values
	('not applicable', currval('observation_types_id_seq'), null),
	('very unclearly', currval('observation_types_id_seq'), lastval()),
	('unclearly', currval('observation_types_id_seq'), lastval()),
	('clearly', currval('observation_types_id_seq'), lastval()),
	('very clearly', currval('observation_types_id_seq'), lastval());
	

INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('jargon', 'How technical is the content?', false);

INSERT INTO observation_values(value, type, next_value)
VALUES
	('not applicable', currval('observation_types_id_seq'), null),
	('not technical', currval('observation_types_id_seq'), lastval()),
	('somewhat technical', currval('observation_types_id_seq'), lastval()),
	('technical', currval('observation_types_id_seq'), lastval()),
	('very technical', currval('observation_types_id_seq'), lastval());
	
    
INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('originality', 'How original is this book?', false);

INSERT INTO observation_values(value, type, next_value)
VALUES
	('not applicable', currval('observation_types_id_seq'), null),
	('very unoriginal', currval('observation_types_id_seq'), lastval()),
	('somewhat unoriginal', currval('observation_types_id_seq'), lastval()),
	('somewhat original', currval('observation_types_id_seq'), lastval()),
	('very original', currval('observation_types_id_seq'), lastval());
	
    
INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('difficulty', 'How advanced is the subject matter of this book?', false);

INSERT INTO observation_values(value, type, next_value)
VALUES
	('not applicable', currval('observation_types_id_seq'), null),
	('requires domain expertise', currval('observation_types_id_seq'), lastval()),
	('a lot of prior knowledge needed', currval('observation_types_id_seq'), lastval()),
	('some prior knowledge needed', currval('observation_types_id_seq'), lastval()),
	('no prior knowledge needed', currval('observation_types_id_seq') , lastval());
	

INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('usefulness', 'How useful is the content of this book?', false);

INSERT INTO observation_values(value, type, next_value)
VALUES
	('not applicable', currval('observation_types_id_seq'), null),
	('not useful', currval('observation_types_id_seq'), lastval()),
	('somewhat useful', currval('observation_types_id_seq'), lastval()),
	('useful', currval('observation_types_id_seq'), lastval()),
	('very useful', currval('observation_types_id_seq'), lastval());
	
    
INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('coverage', 'Does this book''s content cover more breadth or depth of the subject matter?', false);

INSERT INTO observation_values(value, type, next_value)
VALUES
	('not applicable', currval('observation_types_id_seq'), null),
	('much more deep', currval('observation_types_id_seq'), lastval()),
	('somewhat more deep', currval('observation_types_id_seq'), lastval()),
	('equally broad and deep', currval('observation_types_id_seq'), lastval()),
	('somewhat more broad', currval('observation_types_id_seq'), lastval()),
	('much more broad', currval('observation_types_id_seq'), lastval());
	
    
INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('objectivity', 'Are there causes to question the accuracy of this book?', true);

INSERT INTO observation_values(value, type, next_value)
VALUES
	('not applicable', currval('observation_types_id_seq'), null),
	('no, it seems accurate', currval('observation_types_id_seq'), lastval()),
	('yes, it needs citations', currval('observation_types_id_seq'), lastval()),
	('yes, it is inflammatory', currval('observation_types_id_seq'), lastval()),
	('yes, it has typos', currval('observation_types_id_seq'), lastval()),
	('yes, it is inaccurate', currval('observation_types_id_seq'), lastval()),
	('yes, it is misleading', currval('observation_types_id_seq'), lastval()),
	('yes, it is biased', currval('observation_types_id_seq'), lastval());

    
INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('genres', 'What are the genres of this book?', true);

INSERT INTO observation_values(value, type, next_value)
VALUES
	('sci-fi', currval('observation_types_id_seq'), null),
	('philosophy', currval('observation_types_id_seq'), lastval()),
	('satire', currval('observation_types_id_seq'), lastval()),
	('poetry', currval('observation_types_id_seq'), lastval()),
	('memoir', currval('observation_types_id_seq'), lastval()),
	('paranormal', currval('observation_types_id_seq'), lastval()),
	('mystery', currval('observation_types_id_seq'), lastval()),
	('humor', currval('observation_types_id_seq'), lastval()),
	('horror', currval('observation_types_id_seq'), lastval()),
	('fantasy', currval('observation_types_id_seq'), lastval()),
	('drama', currval('observation_types_id_seq'), lastval()),
	('crime', currval('observation_types_id_seq'), lastval()),
	('graphical', currval('observation_types_id_seq'), lastval()),
	('classic', currval('observation_types_id_seq'), lastval()),
	('anthology', currval('observation_types_id_seq'), lastval()),
	('action', currval('observation_types_id_seq'), lastval()),
	('romance', currval('observation_types_id_seq'), lastval()),
	('how-to', currval('observation_types_id_seq'), lastval()),
	('encyclopedia', currval('observation_types_id_seq'), lastval()),
	('dictionary', currval('observation_types_id_seq'), lastval()),
	('technical', currval('observation_types_id_seq'), lastval()),
	('reference', currval('observation_types_id_seq'), lastval()),
	('textbook', currval('observation_types_id_seq'), lastval()),
	('biographical', currval('observation_types_id_seq'), lastval());
	
    
INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('fictionality', 'Is this book a work of fact or fiction?', false);

INSERT INTO observation_values(value, type, next_value)
VALUES
	('nonfiction', currval('observation_types_id_seq'), null),
	('fiction', currval('observation_types_id_seq'), lastval()),
	('biography', currval('observation_types_id_seq'), lastval());
	
    
INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('audience', 'What are the intended age groups for this book?', true);

INSERT INTO observation_values(value, type, next_value)
VALUES
	('experts', currval('observation_types_id_seq'), null),
	('college', currval('observation_types_id_seq'), lastval()),
	('high school', currval('observation_types_id_seq'), lastval()),
	('elementary', currval('observation_types_id_seq'), lastval()),
	('kindergarten', currval('observation_types_id_seq'), lastval()),
	('baby', currval('observation_types_id_seq'), lastval()),
	('general audiences', currval('observation_types_id_seq'), lastval());
	
    
INSERT INTO observation_types(type, description, allow_multiple_values)
VALUES ('mood', 'What are the moods of this book?', true);

INSERT INTO observation_values(value, type, next_value)
VALUES
	('scientific', currval('observation_types_id_seq'), null),
	('dry', currval('observation_types_id_seq'), lastval()),
	('emotional', currval('observation_types_id_seq'), lastval()),
	('strange', currval('observation_types_id_seq'), lastval()),
	('suspenseful', currval('observation_types_id_seq'), lastval()),
	('sad', currval('observation_types_id_seq'), lastval()),
	('dark', currval('observation_types_id_seq'), lastval()),
	('lonely', currval('observation_types_id_seq'), lastval()),
	('tense', currval('observation_types_id_seq'), lastval()),
	('fearful', currval('observation_types_id_seq'), lastval()),
	('angry', currval('observation_types_id_seq'), lastval()),
	('hopeful', currval('observation_types_id_seq'), lastval()),
	('lighthearted', currval('observation_types_id_seq'), lastval()),
	('calm', currval('observation_types_id_seq'), lastval()),
	('informative', currval('observation_types_id_seq'), lastval()),
	('ominous', currval('observation_types_id_seq'), lastval()),
	('mysterious', currval('observation_types_id_seq'), lastval()),
	('romantic', currval('observation_types_id_seq'), lastval()),
	('whimsical', currval('observation_types_id_seq'), lastval()),
	('idyllic', currval('observation_types_id_seq'), lastval()),
	('melancholy', currval('observation_types_id_seq'), lastval()),
	('humorous', currval('observation_types_id_seq'), lastval()),
	('gloomy', currval('observation_types_id_seq'), lastval()),
	('reflective', currval('observation_types_id_seq'), lastval()),
	('inspiring', currval('observation_types_id_seq'), lastval()),
	('cheerful', currval('observation_types_id_seq'), lastval());
