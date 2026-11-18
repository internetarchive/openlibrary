CREATE TEMP TABLE tmp_table
AS
SELECT * FROM test  -- noqa: AM04
WITH NO DATA;
-- 0s

COPY tmp_table FROM :source
WITH (FORMAT csv, DELIMITER E'\t', QUOTE E'\b');
-- <1 min for ~1 Month (363877 rows)

INSERT INTO test
SELECT * FROM tmp_table  -- noqa: AM04
ON CONFLICT ("Key") DO UPDATE SET
    "Type" = EXCLUDED."Type",
    "Revision" = EXCLUDED."Revision",
    "LastModified" = EXCLUDED."LastModified",
    "JSON" = EXCLUDED."JSON";
-- > ~2.25hrs for ~1 Month (363877 rows)

DROP TABLE tmp_table;
