-- used by olsystem/bin/cron/oldump.sh
-- To run locally:
--     docker compose exec web psql -h db --set=upto="$(date +%Y-%m-%d)" -f scripts/dump-reading-log.sql
COPY (
  SELECT
    concat('/works/OL', bookshelves_books.work_id, 'W') AS work_key,
    CASE
      WHEN (bookshelves_books.edition_id IS NULL) THEN NULL
      ELSE concat('/books/OL', bookshelves_books.edition_id, 'M')
    END AS edition_key,
    bookshelves.name AS name,
    -- Truncate created to day precision as a privacy precaution
    DATE(bookshelves_books.created) AS created
  FROM bookshelves_books
  JOIN bookshelves
    ON bookshelves_books.bookshelf_id = bookshelves.id
  -- By default in postgres, "2010-05-17T10:20:30" <= "2010-05-17" ->> FALSE
  -- We need to go up a day to get <= behaviour
  WHERE bookshelves_books.created <= (:'upto'::date + '1 day'::interval)
) TO stdout WITH (format csv, delimiter E'\t')

