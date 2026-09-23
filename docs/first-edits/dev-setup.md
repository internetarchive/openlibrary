# First Edits: dev setup for the walkthrough

The phase 1 walkthrough at `/contribute` needs a few real editions in the local
database whose ISBNs match the evidence fixtures in
`openlibrary/first_edits/fixtures/evidence/`. Nothing else is required: outside
evidence and the demo set are fixtures, and nothing is saved.

## 1. Seed the demo editions

The demo set is `openlibrary/first_edits/fixtures/demo_books.json`. Each entry is
resolved at request time by ISBN against the local database, so the list shows
whichever demo editions exist locally. Import them through the site's import API
as the dev user:

```bash
curl -s -c /tmp/cookies.txt -X POST "http://localhost:8080/account/login.json" \
  -H "Content-Type: application/json" -d '{"username":"openlibrary","password":"openlibrary"}'

# One record per demo edition. Title, authors, publishers, publish_date, isbn_13,
# number_of_pages and languages, in the import API's shape. Leave a field out to
# create a gap the wizard can fill (the demo set expects: Gatsby and Things Fall
# Apart with no language, Ruptured Histories with no publisher, Fantastic Mr Fox
# with no page count).
curl -s -b /tmp/cookies.txt -X POST http://localhost:8080/api/import \
  -H "Content-Type: application/json" \
  -d '{"title":"Ruptured histories","authors":[{"name":"Sheila Miyoshi Jager"},{"name":"Rana Mitter"}],"publish_date":"2007","isbn_13":["9780674024700"],"number_of_pages":384,"languages":["eng"],"subtitle":"war, memory, and the post-Cold War in Asia","source_records":["first-edits-demo:9780674024700"]}'
```

The production records for all eight demo editions are in Bookie's golden
snapshots (`openlibrary-bookie/data/golden/snapshots/*.json`, under
`subject.raw`), which is where the fixtures came from.

## 2. Seed sibling editions

Sibling counts ("how the other editions of this work spell the publisher") are
live, so each demo work needs a few other editions locally. Import three to six
real editions of each work from production the same way; the importer attaches
them to the existing local work by title and author. Skip editions whose
publisher is "Independently Published": the importer rejects them.

## 3. Gate

Every page except `/contribute/start` requires a beta tester or admin. The dev
user `openlibrary` is an admin, so it is already allowed.

## 4. Assets

No asset watcher runs in the dev container. After changing the stylesheet or the
script, rebuild inside the web container and reload:

```bash
docker compose exec web make css
docker compose exec web make js
```

A new Templetor template or plugin module needs `docker compose restart web`.

## Covers

Local cover ids point at the wrong images in dev, so demo books
carry a production `cover_id` in their fixture and load covers from the
production cover CDN.
