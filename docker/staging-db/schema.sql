-- Schema for the isolated BookWorm staging database (#12655 / #12844).
--
-- This DB is separate from production Open Library so bulk feed harvesting
-- never contends with the live catalog. The bookworm service points its DB
-- connection here.
--
-- Contents:
--   * tbp_staged_record — raw normalized feed records (+ acquisition metadata)
--     awaiting promotion into the catalog.
--   * import_batch / import_item — the bookworm-side import queue; manage-imports
--     drains BOTH these and the legacy main-schema tables (dual-source).

CREATE TABLE tbp_staged_record (
    id serial primary key,
    provider_name text not null,
    local_id text not null,
    -- the normalized import record (the "olbook")
    record jsonb not null,
    -- provider acquisition metadata (price/formats/url); travels with the
    -- record so the post-import step can attach it once the edition exists.
    acquisition jsonb default null,
    status text not null default 'staged',  -- staged | promoted | failed
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    UNIQUE (provider_name, local_id)
);

CREATE INDEX tbp_staged_record_status_idx ON tbp_staged_record (status);

-- Bookworm-side import queue (mirrors the main-schema import tables so
-- manage-imports can drain both).
CREATE TABLE import_batch (
    id serial primary key,
    name text,
    submitter text,
    submit_time timestamp without time zone default (current_timestamp at time zone 'utc')
);

CREATE INDEX import_batch_name ON import_batch (name);

CREATE TABLE import_item (
    id serial primary key,
    batch_id integer references import_batch,
    added_time timestamp without time zone default (current_timestamp at time zone 'utc'),
    import_time timestamp without time zone,
    status text default 'pending',
    error text,
    ia_id text,
    data text,
    ol_key text,
    comments text,
    submitter text,
    UNIQUE (batch_id, ia_id)
);

CREATE INDEX import_item_ia_id ON import_item (ia_id);
CREATE INDEX import_item_status ON import_item (status);
