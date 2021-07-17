psql -U openlibrary -d openlibrary -c "COPY (
  SELECT
    concat('/works/OL', bookshelves_books.work_id, 'W') AS work_id,
    CASE
      WHEN (bookshelves_books.edition_id IS NULL) THEN NULL
      ELSE concat('/books/OL', bookshelves_books.edition_id, 'M')
    END AS edition_id,
    bookshelves.name AS name,
    DATE_TRUNC('day', bookshelves_books.created) AS created
  FROM bookshelves_books
  JOIN bookshelves
    ON bookshelves_books.bookshelf_id = bookshelves.id
  WHERE bookshelves_books.created <= '$date'
) TO stdout WITH (format csv, header, delimiter E'\t')"