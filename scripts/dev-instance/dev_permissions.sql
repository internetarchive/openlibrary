-- Seed the production edit policy for catalog records.
--
-- The committed dev dump only contains the bootstrap permission documents
-- (/permission/open, /permission/restricted, and /permission/secret). As a
-- result, a fresh dev database lets anonymous users edit catalog records even
-- though production requires a logged-in account.
--
-- This file is loaded by docker/ol-db-init.sh after scripts/dev-instance/dev_db.pg_dump.

BEGIN;

-- /permission/loggedinusers is the "Only loggedin users can edit" policy.
WITH new_permission AS (
    INSERT INTO thing (key, type, latest_revision, created, last_modified)
    SELECT
        '/permission/loggedinusers',
        permission_type.id,
        1,
        timezone('utc', now()),
        timezone('utc', now())
    FROM thing AS permission_type
    WHERE permission_type.key = '/type/permission'
      AND NOT EXISTS (
          SELECT 1
          FROM thing
          WHERE thing.key = '/permission/loggedinusers'
      )
    RETURNING id
)

INSERT INTO data (thing_id, revision, data)
SELECT
    id,
    1,
    jsonb_build_object(
        'key', '/permission/loggedinusers',
        'type', jsonb_build_object('key', '/type/permission'),
        'readers', jsonb_build_array(
            jsonb_build_object('key', '/usergroup/everyone')
        ),
        'writers', jsonb_build_array(
            jsonb_build_object('key', '/usergroup/allusers')
        ),
        'admins', jsonb_build_array(
            jsonb_build_object('key', '/usergroup/admin')
        ),
        'latest_revision', 1,
        'revision', 1,
        'created', jsonb_build_object(
            'type', '/type/datetime',
            'value', to_char(timezone('utc', now()), 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ),
        'last_modified', jsonb_build_object(
            'type', '/type/datetime',
            'value', to_char(timezone('utc', now()), 'YYYY-MM-DD"T"HH24:MI:SS.US')
        )
    )::text
FROM new_permission;

-- Match production's catalog policy: the /books, /works, and /authors pages
-- themselves are admin-only, while their child records are editable by anyone
-- who is logged in.
WITH catalog_pages (key) AS (
    VALUES ('/books'), ('/works'), ('/authors')
),

new_pages AS (
    INSERT INTO thing (key, type, latest_revision, created, last_modified)
    SELECT
        catalog_pages.key,
        page_type.id,
        1,
        timezone('utc', now()),
        timezone('utc', now())
    FROM catalog_pages
    CROSS JOIN thing AS page_type
    WHERE page_type.key = '/type/page'
      AND NOT EXISTS (
          SELECT 1
          FROM thing
          WHERE thing.key = catalog_pages.key
      )
    RETURNING id, key
)

INSERT INTO data (thing_id, revision, data)
SELECT
    id,
    1,
    jsonb_build_object(
        'key', key,
        'type', jsonb_build_object('key', '/type/page'),
        'permission', jsonb_build_object('key', '/permission/restricted'),
        'child_permission', jsonb_build_object('key', '/permission/loggedinusers'),
        'latest_revision', 1,
        'revision', 1,
        'created', jsonb_build_object(
            'type', '/type/datetime',
            'value', to_char(timezone('utc', now()), 'YYYY-MM-DD"T"HH24:MI:SS.US')
        ),
        'last_modified', jsonb_build_object(
            'type', '/type/datetime',
            'value', to_char(timezone('utc', now()), 'YYYY-MM-DD"T"HH24:MI:SS.US')
        )
    )::text
FROM new_pages;

-- Record the seed revisions in infobase history, matching the synthetic
-- transaction-less rows used by the committed dump.
INSERT INTO version (thing_id, revision, transaction_id)
SELECT
    thing.id,
    1,
    NULL
FROM thing
WHERE thing.key IN (
    '/permission/loggedinusers',
    '/books',
    '/works',
    '/authors'
)
AND NOT EXISTS (
    SELECT 1 FROM version
    WHERE version.thing_id = thing.id AND version.revision = 1
);

COMMIT;
