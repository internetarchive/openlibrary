CREATE TEMP TABLE tmp_table
AS
SELECT * FROM entity
WITH NO DATA;
-- 0s

COPY tmp_table FROM :source
WITH delimiter E'\t' quote E'\b' csv;
-- <1 min for ~1 Month (363877 rows)

INSERT INTO entity
SELECT * FROM tmp_table
ON CONFLICT (keyid) DO UPDATE SET
    etype = EXCLUDED.etype,
    revision = EXCLUDED.revision,
    last_modified = EXCLUDED.last_modified,
    content = EXCLUDED.content;
-- > ~2.25hrs for ~1 Month (363877 rows)

DROP TABLE tmp_table;
