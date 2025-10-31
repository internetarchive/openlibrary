-- used by olsystem/bin/cron/oldump.sh
-- To run locally:
--     docker compose exec web psql -h db --set=upto="$(date +%Y-%m-%d)" -f scripts/dump-ratings.sql
COPY (
    SELECT
        ratings.rating,
        concat('/works/OL', ratings.work_id, 'W') AS work_key,
        CASE
            WHEN (ratings.edition_id IS NULL) THEN NULL
            ELSE concat('/books/OL', ratings.edition_id, 'M')
        END AS edition_key,
        -- Truncate created to day precision as a privacy precaution
        date(ratings.created) AS created
    FROM ratings
    -- By default in postgres, "2010-05-17T10:20:30" <= "2010-05-17" ->> FALSE
    -- We need to go up a day to get <= behaviour
    WHERE ratings.created <= (: 'upto'::date + '1 day'::interval)
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t')
