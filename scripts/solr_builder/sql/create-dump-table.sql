CREATE TABLE test (
    "Type" character varying(255) NOT NULL,
    "Key" character varying(255) NOT NULL,
    "Revision" integer NOT NULL,
    "LastModified" timestamp without time zone NOT NULL,
    "JSON" jsonb NOT NULL
);