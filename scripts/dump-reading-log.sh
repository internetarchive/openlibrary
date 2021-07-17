psql -U openlibrary -d openlibrary -c "COPY (
  SELECT
  concat('OL', work_id, 'W') AS work_id,
  CASE
    WHEN (ratings.edition_id IS NULL) THEN NULL
    ELSE concat('OL', ratings.edition_id, 'M')
  END AS edition_id,
  DATE_TRUNC('day', ratings.created) AS created,
  ratings.rating AS rating
  FROM ratings
  WHERE ratings.created <= '$date'
) TO stdout WITH (format csv, header, delimiter E'\t')"