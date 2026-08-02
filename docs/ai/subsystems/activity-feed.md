# Activity Feed

The social feed of what patrons publicly do with books. Backs the "My Feed" section on My Books and the standalone `/people/{username}/books/feed` page. Epic: [#10242](https://github.com/internetarchive/openlibrary/issues/10242).

## Where the data lives

There is no single event table. Patron activity is spread across three unrelated stores:

| Event | Store | Read via |
|---|---|---|
| Shelved a book | Postgres `bookshelves_books` | `Bookshelves.get_recently_logged_books()`, or `PubSub.get_feed()` for a follow graph |
| Rated a book | Postgres `ratings` | `Ratings.get_recent_ratings()` |
| Liked a list | Postgres `likes` | `Likes.get_recent_likes()` |
| Created or changed a list | Infogami things (`/type/list`) | `site.get().things({"type": "/type/list", "sort": "-last_modified"})` |
| Borrowed a book | Infogami store + archive.org | Per-user only. **No public global source.** |

`openlibrary/core/activity.py` normalises each into one `ActivityEvent` and merges them time-ordered.

```python
from openlibrary.core.activity import ActivityStream

events = ActivityStream.public_feed(viewer="mekBot", limit=12)
events = ActivityStream.following_feed("mekBot", limit=12)
ActivityStream.attach_works(events)  # fills in each event's Solr work record
```

`public_feed` restricts to patrons who opted into a public reading log and drops the viewer's own activity. `following_feed` restricts to who the viewer follows and **deliberately does not re-apply the public-reading-log filter** — following is consent, so a private log still reaches the people the patron chose to publish to.

A rating on a book the same patron just shelved folds onto the shelving rather than emitting a second near-identical card.

## API

`GET /api/internal/activity/feed.json` (`openlibrary/fastapi/activity.py`)

| Param | Default | Notes |
|---|---|---|
| `limit` | 12 | 1–50 |
| `page` | 1 | |
| `scope` | `auto` | `auto` picks following-or-public from the viewer; `public` and `following` force it |

Returns `{scope, following, page, activity: [...]}`. Every item carries `type`, `username`, `patron_url`, `avatar_url`, `created`, `label`, and optionally `shelf_url`, `rating`, `work`, `list`. One shape serves every rendering of the feed, so a card means the same thing wherever it appears.

## Frontend

`<ol-social-feed>` — `openlibrary/components/lit/OlSocialFeed.js`.

**Every activity type renders into one card skeleton**, following Goodreads' Updates panel:

```
avatar   Actor  verb  target                        when   [Follow]
         ┌───────┐  Title
         │ media │  subtitle
         └───────┘  [primary action] [secondary]  ★★★★☆
```

A shelving fills `media` with a book cover and `verb` with the shelf; a list update fills `media` with a fan of three covers and `subtitle` with a book count; a like fills the same slots from the liked list. Nothing about the frame changes.

`_present(item)` is the only place that knows how the types differ — it maps an event onto `{href, covers, title, subtitle, actions}`. **Adding an event type means one `_present` branch, not a new template.** Layout variants are CSS over that single markup, so a card means the same thing to a reader wherever it appears.

Two consequences worth knowing:

- Do not branch on `item.type` in the template. Branch on the *shape* (`item.list` vs `item.work`) inside `_present`, so a new type that produces a list card needs no template change — this is how likes reuse the list rendering.
- A backtick anywhere inside the `css` tagged template silently ends the literal, and the build fails with a bare `Missing semicolon` pointing far from the cause. Do not put code ticks in CSS comments.

**Not to be confused with `<ol-activity-feed>`**, which is the homepage "What's Happening Now" widget ([#12863](https://github.com/internetarchive/openlibrary/pull/12863)). Different surfaces, shared patterns.

## Traps

**Covers must come from the Solr record's `cover_i`.** Building a cover URL from a work OLID (`//covers.openlibrary.org/w/olid/OL{work_id}W-M.jpg`) renders the *wrong* books — a real bug on [#11391](https://github.com/internetarchive/openlibrary/pull/11391).

**`PubSub.get_feed()` reads `bookshelves_books` only.** It is a reading-log query filtered by the follow graph, not a general feed. Any event type beyond shelving is new work for the following case too.

**`likes.key` is a generic Infogami key** with no foreign key and no type validation — it can name a work, a list, an author, or nothing at all. Validate the shape and handle a deleted target.

**`public_readlog` lives in the Infogami store**, at `/people/{username}/preferences`. There is no Postgres column for it.

**In dev, web.py cannot reach FastAPI on the same origin.** Production nginx routes `/api/internal/*` to the FastAPI process; a local stack has no proxy between ports 8080 and 18080. Pass the FastAPI origin explicitly when a web.py-rendered page needs the endpoint locally.

## Local test data

The stock dev seed creates one account, so there is no social graph, and a fresh dev Solr has ~35 works with no cover ids — a populated feed still renders as grey boxes. This is why three prior UI attempts were closed without anyone seeing a real feed.

```bash
docker compose run --rm home python scripts/dev-instance/seed_social_feed.py
docker compose run --rm home python scripts/dev-instance/seed_social_feed.py --no-follows  # public-feed mode
```

Seeds real cover-bearing works into Solr *and* Infogami, six patrons with public reading logs, plus shelvings, ratings, lists, likes, and a follow graph. Idempotent.

Two things any script writing to Infogami needs to know, learned here:

- **`setup_for_script` does not set `web.ctx.ip`.** Infogami writes it to `transaction.ip`, a Postgres `inet` column, and rejects the empty string — so the write 500s with `invalid input syntax for type inet`. Set `web.ctx.ip = "127.0.0.1"` after calling it.
- **`User.new_list()` does not save**; the caller must `_save()`. Its seeds must point at works that exist as Infogami things, not just Solr docs, or the save fails with a bare `KeyError` on the seed key.

## Tests

```bash
docker compose run --rm home python -m pytest openlibrary/core/tests/test_activity.py openlibrary/tests/fastapi/test_activity_feed.py

# End to end, against seeded data. The dev stack has no web.py -> FastAPI proxy,
# so the endpoint origin is passed in.
OL_FEED_API=http://localhost:18080/api/internal/activity/feed.json npx playwright test tests/e2e/activity-feed.spec.ts
```

The Playwright suite asserts the **populated** state specifically. An empty feed passing as "it renders" is the failure mode that closed the prior attempts.
