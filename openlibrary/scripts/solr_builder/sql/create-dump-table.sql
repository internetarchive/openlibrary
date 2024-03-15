CREATE TABLE test (
    "Type" character varying(255) NOT NULL,
    "Key" character varying(255) NOT NULL,
    "Revision" integer NOT NULL,
    "LastModified" timestamp without time zone NOT NULL,
    "JSON" jsonb NOT NULL
);

CREATE TABLE ratings (
    "WorkKey" character varying(255) NOT NULL,
    "EditionKey" character varying(255),
    "Rating" numeric(2, 1),
    "Date" date NOT NULL
);

CREATE TABLE reading_log (
    "WorkKey" character varying(255) NOT NULL,
    "EditionKey" character varying(255),
    "Shelf" character varying(255),
    "Date" date NOT NULL
)
