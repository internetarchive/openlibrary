CREATE TEMP TABLE tmp_table
AS
SELECT * FROM test
WITH NO DATA;
-- 0s

COPY tmp_table FROM :source
WITH delimiter E'\t' quote E'\b' csv;
-- <1 min for ~1 Month (363877 rows)

INSERT INTO test
SELECT * FROM tmp_table
ON CONFLICT ("Key") DO UPDATE SET
    "Type" = EXCLUDED."Type",
    "Revision" = EXCLUDED."Revision",
    "LastModified" = EXCLUDED."LastModified",
    "JSON" = EXCLUDED."JSON";
-- > ~2.25hrs for ~1 Month (363877 rows)

DROP TABLE tmp_table;