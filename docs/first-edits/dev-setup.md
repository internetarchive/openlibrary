# First Edits: dev setup

`/contribute` needs no seeding. The lists come from Solr's edition child
documents (editions with an ISBN missing a field, under the most-read works),
and the task page reads the edition and its siblings from the local database.
Nothing is fetched from outside catalogs and nothing is saved.

## What has to be running

- `solr`, with editions indexed. If the lists are empty, check
  `type:edition` returns documents. Solr exits with code 134 under memory
  pressure; `docker compose up -d solr` brings it back.
- `solr-updater`, so a field filled since the last reindex drops out. The page
  also re-checks each edition against the database, so a stale index only
  shortens the list; it never shows a filled field as a task.

## Gate

Every page requires a beta tester, librarian, maintainer or admin. The dev
user `openlibrary` is an admin, so it is already allowed.

## Assets

No asset watcher runs in the dev container. After changing the stylesheet or the
script, rebuild inside the web container and reload:

```bash
docker compose exec web make css
docker compose exec web make js
```

A new Templetor template or plugin module needs `docker compose restart web`.

## Covers

Local cover ids often point at the wrong images in dev. That's a dev-data
problem, not a page bug.
