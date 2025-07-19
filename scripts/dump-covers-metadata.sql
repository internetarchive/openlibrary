-- To run locally:
-- docker compose exec web psql -h db -d coverstore --set=upto="$(date +%Y-%m-%d)" -f scripts/dump-covers-metadata.sql

COPY (
    SELECT
        cover.id,
        cover.width,
        cover.height,
        -- Truncate created to day precision as a privacy precaution
        DATE(cover.created) AS created
    FROM cover
    -- By default in postgres, "2010-05-17T10:20:30" <= "2010-05-17" ->> FALSE
    -- We need to go up a day to get <= behaviour
    WHERE cover.created <= (: 'upto'::date + '1 day'::interval)
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t')
