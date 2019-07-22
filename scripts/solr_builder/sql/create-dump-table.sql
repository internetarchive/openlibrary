CREATE TYPE type_enum as ENUM (
 '/type/edition',
 '/type/work',
 '/type/author',
 '/type/delete',
 '/type/redirect',
 '/type/subject',
 '/type/i18n',
 '/type/language',
 '/type/library',
 '/type/template',
 '/type/page',
 '/type/macro',
 '/type/volume',
 '/type/type',
 '/type/rawtext',
 '/type/i18n_page',
 '/type/usergroup',
 '/type/home',
 '/type/permission',
 '/type/doc',
 '/type/backreference',
 '/type/series',
 '/type/local_id',
 '/type/collection',
 '/type/user',
 '/type/scan_record',
 '/type/uri',
 '/type/scan_location',
 '/type/place',
 '/type/object',
 '/type/content',
 '/type/about'
);

CREATE TABLE entity (
    etype type_enum NOT NULL, -- entity type
    keyid varchar NOT NULL, -- entity key/id
    revision integer NOT NULL,
    last_modified timestamp without time zone NOT NULL,
    content jsonb NOT NULL -- full jsonb so we can use operators
);
