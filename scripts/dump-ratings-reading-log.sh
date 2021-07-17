psql -U openlibrary -d openlibrary -c "copy (
  select
  concat('/works/OL', bookshelves_books.work_id, 'W') as work_id,
  case
    when (bookshelves_books.edition_id is NULL)
    then NULL
    else concat('/books/OL', bookshelves_books.edition_id, 'M')
  end as edition_id,
  bookshelves.name as name,
  bookshelves_books.created as created
  from bookshelves_books
  join bookshelves on bookshelves_books.bookshelf_id = bookshelves.id
) to stdout with (format csv, header, delimiter E'\t')" | gzip -c > reading-log.txt.gz
psql -U openlibrary -d openlibrary -c "copy (
  select
  concat('OL', work_id, 'W') as work_id,
  case
    when (ratings.edition_id is NULL)
    then NULL
    else concat('OL', ratings.edition_id, 'M')
  end as edition_id,
  ratings.created as created,
  ratings.rating as rating
  from ratings
) to stdout with (format csv, header, delimiter E'\t')" | gzip -c > ratings.txt.gz
