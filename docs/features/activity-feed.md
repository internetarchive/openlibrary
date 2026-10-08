# Activity Feed

The social feed of what patrons publicly do with books: shelve them, rate them, gather them into lists. It backs the "My Feed" section on My Books and the standalone `/people/{username}/books/feed` page.

Tracked by [#10242](https://github.com/internetarchive/openlibrary/issues/10242) (epic). Related: [#8607](https://github.com/internetarchive/openlibrary/pull/8607) added the follow feature and the original feed page.

## Where the data actually lives

This is the thing that surprises people. Patron activity is scattered across three unrelated stores, and there is no single event table:

| Event | Store | How to read it |
|---|---|---|
| Shelved a book (Want to Read / Currently Reading / Already Read) | Postgres `bookshelves_books` | `Bookshelves.get_recently_logged_books()` for the whole library; `PubSub.get_feed()` for a viewer's follow graph |
| Rated a book | Postgres `ratings` | `Ratings.get_recent_ratings()` |
| Created or changed a list | **Infogami things** (`/type/list`), not Postgres | `site.get().things({"type": "/type/list", "sort": "-last_modified"})` |
| Borrowed a book | Infogami store + archive.org | Per-user only (`get_loans_of_user`). **No public global source exists.** |
| Liked (upvoted) a list | Postgres `likes` | `Likes.get_recent_likes()`. Landed [#12932](https://github.com/internetarchive/openlibrary/pull/12932), 2026-07-31. Distinct from list *following* (`lists/list_follow.html`). |

`openlibrary/core/activity.py` normalises all of these into one `ActivityEvent` shape and merges them time-ordered. Two entry points:

- `ActivityStream.public_feed(viewer)` — everything across the library, restricted to patrons who opted into a public reading log, excluding the viewer's own activity.
- `ActivityStream.following_feed(viewer)` — the same, restricted to who the viewer follows. **Deliberately does not re-apply the public-reading-log filter**: following is consent, so a private reading log still reaches the people the patron chose to publish to.

Rating a book you just marked read is one act to a reader, so the star folds onto the matching shelving rather than emitting two near-identical cards.

## Gotchas

**`PubSub.get_feed()` only reads `bookshelves_books`.** It is not a general feed — it is a reading-log query filtered by the follow graph. Any event type beyond shelving is new work for the following case, not just the public one.

**Covers must come off the Solr record's `cover_i`.** Guessing `//covers.openlibrary.org/w/olid/OL{work_id}W-M.jpg` renders the *wrong* books. This was a real bug on [#11391](https://github.com/internetarchive/openlibrary/pull/11391) and jimchamp's fix note is the reason the enrichment step fetches `cover_i` explicitly.

**`public_readlog` gates the public feed.** A patron whose reading log is private is filtered straight back out. Read it from the Infogami store at `/people/{username}/preferences`; there is no Postgres column for it.

**`likes.key` is a generic Infogami key with no foreign key and no type validation.** It can name a work, edition, author, list, or a string that resolves to nothing at all — `openlibrary/plugins/upstream/likes.py` rejects none of it. Anything reading `likes` has to validate the shape itself and cope with a target that has since been deleted. By convention (scope decision 2026-07-29) it is used for lists only.

**Avatars need a linked archive.org account.** `User.get_avatar_url()` reads `internetarchive_itemname` off the account record and builds `https://archive.org/services/img/{itemname}`. An account with no link produces a broken URL, so callers should be defensive.

## Testing it locally — the hard part

Three attempts at the UI ([#11290](https://github.com/internetarchive/openlibrary/pull/11290), [#11391](https://github.com/internetarchive/openlibrary/pull/11391), [#11645](https://github.com/internetarchive/openlibrary/pull/11645)) were all closed without anyone producing a real, populated, correctly-styled feed. The reason is environmental, not a skill issue:

- the stock `scripts/dev-instance/load-patron-data.sh` seeds the `openlibrary` account **only**, so there is no second patron to follow and no social graph at all
- a fresh dev Solr holds ~35 works, **none with cover ids**, so even a populated feed renders as a column of grey boxes

`scripts/dev-instance/seed_social_feed.py` fixes both:

```bash
docker compose run --rm home python scripts/dev-instance/seed_social_feed.py
docker compose run --rm home python scripts/dev-instance/seed_social_feed.py --no-follows  # public-feed mode
```

It indexes real cover-bearing works into Solr *and* creates them as Infogami things, makes six patrons with public reading logs, and gives them shelvings, ratings, lists, and a follow graph. Idempotent.

### Two traps it had to work around

**`setup_for_script` does not set `web.ctx.ip`.** Infogami writes the caller's IP into `transaction.ip`, a Postgres `inet` column, and an empty string is rejected — so *every* script that writes to Infogami dies with `invalid input syntax for type inet`. Set `web.ctx.ip = "127.0.0.1"` after `setup_for_script()`.

**`User.new_list()` does not save.** It only builds the doc; the caller must call `lst._save(...)`. And list seeds must reference works that exist as **Infogami things** — a list whose seeds point at works only present in Solr fails the save with a bare `KeyError` on the seed key.

### Logging in as another patron

There are no credentials for seeded accounts. Use the admin console: log in as `openlibrary`, go to `/admin/people/{username}`, and press "Login as this user".

## Frontend

`<ol-social-feed>` (`openlibrary/components/lit/OlSocialFeed.js`) renders the feed from `GET /api/internal/activity/feed.json`. One JSON shape serves every rendering, so a card means the same thing wherever it appears.

Note there are **two** activity feed components and they are not the same thing: `<ol-activity-feed>` is the homepage "What's Happening Now" widget ([#12863](https://github.com/internetarchive/openlibrary/pull/12863)); `<ol-social-feed>` is the My Books one. Different surfaces, shared patterns.

In production nginx routes `/api/internal/*` to the FastAPI process. In local dev, FastAPI is the front door on `localhost:8080` and serves `/api/internal/*` directly, proxying any route it doesn't handle to web.py (`openlibrary/fastapi/proxy.py`) — so the endpoint is reachable same-origin at `localhost:8080`, no separate origin needed. (The old web.py-on-8080 / FastAPI-on-18080 layout was swapped in #13423.)
