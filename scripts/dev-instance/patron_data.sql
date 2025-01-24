--
-- PostgreSQL database dump
-- Run the following command to populate this data:
-- ./scripts/dev-instance/load-patron-data.sh

SET statement_timeout = 0;
SET lock_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET client_min_messages = warning;

SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: bookshelves_books; Type: TABLE; Schema: public; Owner: postgres; Tablespace:
--

CREATE TABLE IF NOT EXISTS public.bookshelves_books (
    username text NOT NULL,
    work_id integer NOT NULL,
    bookshelf_id integer NOT NULL,
    edition_id integer,
    private boolean,
    updated timestamp without time zone DEFAULT timezone('utc'::text, now()),
    created timestamp without time zone DEFAULT timezone('utc'::text, now())
);


--
-- Name: observations; Type: TABLE; Schema: public; Owner: postgres; Tablespace:
--

CREATE TABLE IF NOT EXISTS public.observations (
    work_id integer NOT NULL,
    edition_id integer DEFAULT (-1) NOT NULL,
    username text NOT NULL,
    observation_type integer NOT NULL,
    observation_value integer NOT NULL,
    created timestamp without time zone DEFAULT timezone('utc'::text, now())
);

--
-- Name: ratings; Type: TABLE; Schema: public; Owner: postgres; Tablespace:
--

CREATE TABLE IF NOT EXISTS public.ratings (
    username text NOT NULL,
    work_id integer NOT NULL,
    rating integer,
    edition_id integer,
    updated timestamp without time zone DEFAULT timezone('utc'::text, now()),
    created timestamp without time zone DEFAULT timezone('utc'::text, now())
);


--
-- Data for Name: bookshelves_books; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.bookshelves_books (username, work_id, bookshelf_id, edition_id, private, updated, created) FROM stdin;
openlibrary	15298516	1	\N	\N	2025-01-02 23:27:07.387947	2025-01-02 23:27:07.387947
openlibrary	45310	3	\N	\N	2025-01-02 23:27:13.807905	2025-01-02 23:27:13.807905
openlibrary	15692545	2	24620876	\N	2025-01-02 23:27:25.025792	2025-01-02 23:27:25.025792
openlibrary	20600	3	24173003	\N	2025-01-02 23:52:19.822275	2025-01-02 23:52:19.822275
\.


--
-- Data for Name: observations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.observations (work_id, edition_id, username, observation_type, observation_value, created) FROM stdin;
20600	-1	openlibrary	16	3	2025-01-03 01:54:54.331777
20600	-1	openlibrary	1	5	2025-01-03 01:54:57.946027
20600	-1	openlibrary	2	9	2025-01-03 01:55:01.624478
20600	-1	openlibrary	3	7	2025-01-03 01:55:03.717624
20600	-1	openlibrary	6	7	2025-01-03 01:55:07.345592
20600	-1	openlibrary	8	9	2025-01-03 01:55:13.720668
20600	-1	openlibrary	10	3	2025-01-03 01:56:05.82709
20600	-1	openlibrary	10	1	2025-01-03 01:56:13.577915
20600	-1	openlibrary	13	22	2025-01-03 01:56:20.620139
20600	-1	openlibrary	14	9	2025-01-03 01:56:25.61887
20600	-1	openlibrary	20	5	2025-01-03 01:56:47.841587
20600	-1	openlibrary	21	1	2025-01-03 01:56:53.147454
20600	-1	openlibrary	21	2	2025-01-03 01:56:54.292912
45310	-1	openlibrary	10	25	2025-01-03 01:58:22.199135
45310	-1	openlibrary	10	16	2025-01-03 01:58:32.415716
45310	-1	openlibrary	6	7	2025-01-03 01:59:09.200272
45310	-1	openlibrary	16	3	2025-01-03 02:01:43.487236
45310	-1	openlibrary	14	1	2025-01-03 02:02:08.344129
45310	-1	openlibrary	1	4	2025-01-03 02:03:24.430176
45310	-1	openlibrary	3	7	2025-01-03 02:04:31.84614
45310	-1	openlibrary	2	7	2025-01-03 02:06:26.167173
\.


--
-- Data for Name: ratings; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.ratings (username, work_id, rating, edition_id, updated, created) FROM stdin;
openlibrary	20600	4	24173003	2025-01-02 23:52:19.824507	2025-01-02 23:52:19.824507
openlibrary	45310	3	24152177	2025-01-02 23:51:21.832977	2025-01-02 23:51:21.832977
\.

--
-- Data for Name: thing; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.seq (name, value) VALUES ('list', 1);

INSERT INTO public.thing (key, type, latest_revision) VALUES ('/people/openlibrary/lists/OL1L', 35, 1);

INSERT INTO public.transaction (action, author_id, ip, comment, changes, data) VALUES ('lists', 524, '172.19.0.1', '', '[{"key": "/people/openlibrary/lists/OL1L", "revision": 1}]', '{}');

INSERT INTO public.version (thing_id, revision, transaction_id) VALUES ((SELECT id FROM public.thing WHERE key ='/people/openlibrary/lists/OL1L'), 1, (SELECT id FROM public.transaction WHERE action = 'lists'));

INSERT INTO public.data (thing_id, revision, data) VALUES ((SELECT id FROM public.thing WHERE key = '/people/openlibrary/lists/OL1L'), 1, '{"key": "/people/openlibrary/lists/OL1L", "type": {"key": "/type/list"}, "name": "OpenLibrary Test List", "description": {"type": "/type/text", "value": "Lorem ipsum dolor sit amet"}, "seeds": [{"key": "/works/OL20600W"}, {"key": "/works/OL45310W"}, {"key": "/books/OL24293426M"}, {"key": "/books/OL6514192M"}, {"key": "/works/OL61982W"}], "latest_revision": 1, "revision": 1, "created": {"type": "/type/datetime", "value": "2025-01-03T20:50:27.524685"}, "last_modified": {"type" :"/type/datetime", "value": "2025-01-03T20:50:27.524685"}}');

INSERT INTO public.property (name, type) VALUES ('seeds', 35);
INSERT INTO public.property (name, type) VALUES ('name', 35);

INSERT INTO public.datum_str(key_id, thing_id, value) VALUES ((SELECT id FROM public.property WHERE type=35 AND name='name'), (SELECT id FROM public.thing WHERE key = '/people/openlibrary/lists/OL1L'), 'OpenLibrary Test List');

INSERT INTO public.datum_ref (key_id, thing_id, value) SELECT * FROM (SELECT id FROM public.property WHERE type=35 AND name='seeds') t1 FULL JOIN (SELECT id FROM public.thing WHERE key='/people/openlibrary/lists/OL1L') t2 ON true FULL JOIN (SELECT id FROM public.thing WHERE key IN ('/works/OL20600W', '/works/OL45310W', '/books/OL24293426M', '/books/OL6514192M', '/works/OL61982W')) t3 ON true;

--
-- PostgreSQL database dump complete
--

