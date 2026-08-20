# Blocking I/O Migration Report

## Branch: `13399/fix/easy-blocking-io-migrations`

This report tracks the migration of 16 "easy" blocking I/O operations from template layer to Python handler layer, as identified in `docs/template_blocking_io_audit.md`.

## Migration Strategy

The goal is to move blocking I/O (DB queries, Solr lookups, HTTP calls) out of templates and into Python handlers, so that:
1. The handler precomputes the data
2. The precomputed data is passed to the template as a parameter
3. The template uses the parameter instead of performing I/O

For macros called from multiple contexts, we add optional parameters that accept precomputed values, maintaining backward compatibility.

## Summary

| Status | Count | Description |
|--------|-------|-------------|
| ✅ Migrated | 8 | Handler precomputes, template uses param |
| ⚠️ Partial | 3 | Mechanism exists but callers need audit/infogami changes |
| 🚫 Blocked | 4 | All callers in infogami vendor code |
| 🗑️ N/A | 1 | Unused macro (no callers) |

## Detailed Migration Results

### ✅ Successfully Migrated (8)

#### Migration 4: `templates/account/mybooks.html`
- **Blocking I/O:** `get_reading_goals(year=year)` — DB query
- **Handler:** `openlibrary/plugins/upstream/mybooks.py` (`mybooks_home`)
- **Change:** Handler precomputes `current_goal` via `get_reading_goals()` and passes to template
- **Files:** `mybooks.py`, `account/mybooks.html`

#### Migration 5: `templates/account/reading_log.html`
- **Blocking I/O:** `get_internet_archive_id(user.key)` — DB lookup via OpenLibraryAccount
- **Handler:** `openlibrary/plugins/upstream/mybooks.py` (`mybooks_readinglog`, `mybooks_feed`)
- **Change:** Handler precomputes `meta_photo_url` and passes to template
- **Files:** `mybooks.py`, `account/reading_log.html`

#### Migration 6: `templates/admin/imports_by_date.html`
- **Blocking I/O:** `stats.get_items_summary(date)` + `stats.get_items(date)` — Import DB queries
- **Handler:** `openlibrary/plugins/admin/code.py` (`imports_by_date`)
- **Change:** Handler precomputes summary and items, passes to template
- **Files:** `admin/code.py`, `admin/imports_by_date.html`

#### Migration 7: `templates/admin/index.html`
- **Blocking I/O:** `get_admin_stats()` — `web.ctx.site.get_many` for admin stats docs
- **Handler:** `openlibrary/views/loanstats.py` (`stats`)
- **Change:** Handler precomputes `admin_stats` and passes to template
- **Files:** `loanstats.py`, `admin/index.html`

#### Migration 8: `templates/authors/index.html`
- **Blocking I/O:** `random_author_search()` — Solr query
- **Handler:** `openlibrary/plugins/openlibrary/authors.py` (`author`)
- **Change:** Handler calls `random_author_search()` and passes `results` to template
- **Files:** `authors.py`, `authors/index.html`

#### Migration 9: `templates/covers/saved.html`
- **Blocking I/O:** `image.info()` — HTTP to coverstore
- **Handler:** `openlibrary/plugins/upstream/covers.py` (`manage_covers`)
- **Change:** Handler precomputes `image_info` and passes to template
- **Files:** `covers.py`, `covers/saved.html`

#### Migration 10: `templates/showia.html`
- **Blocking I/O:** `get_document(books[0])` — DB lookup for breadcrumb
- **Handler:** `openlibrary/views/showmarc.py` (`show_ia`)
- **Change:** Handler precomputes `edition` via `web.ctx.site.get(books[0])` and passes to template
- **Files:** `showmarc.py`, `showia.html`

#### Migration 11: `templates/showmarc.html`
- **Blocking I/O:** `get_document(books[0])` — DB lookup for breadcrumb
- **Handler:** `openlibrary/views/showmarc.py` (`show_marc`)
- **Change:** Handler precomputes `edition` via `web.ctx.site.get(books[0])` and passes to template
- **Files:** `showmarc.py`, `showmarc.html`

### ⚠️ Partially Migrated (3)

#### Migration 1: `macros/StarRatings.html`
- **Blocking I/O:** `work.get_users_rating(username)` — DB lookup
- **Status:** Macro already accepts optional `rating` param. `reading_log` and `loan_history` handlers pass it. Book page callers (modal_links, lists/widget) are rendered from infogami's type system, which cannot be modified to pass the rating.
- **Impact:** Partial — eliminates I/O on reading log and loan history pages. Book pages still have the fallback.

#### Migration 2: `macros/QueryCarousel.html`
- **Blocking I/O:** `convert_iso_to_marc(...)` — DB lookup (all `/type/language` docs)
- **Status:** Already `functools.lru_cache`-decorated — I/O only on first call. Not worth adding a param for cached data.
- **Impact:** Low — effectively free after first call.

#### Migration 3: `macros/RawQueryCarousel.html`
- **Blocking I/O:** `gather_lazy_carousel_data(...)` — Solr query
- **Status:** Pre-fetch mechanism already exists via `books_data` parameter. `LazyCarouselPartial` uses it. Non-lazy callers still call Solr directly in the template. Full migration would require auditing all non-lazy callers.
- **Impact:** Medium — lazy carousels already use pre-fetch. Non-lazy carousels still block.

### 🚫 Blocked by infogami vendor code (4)

#### Migration 12: `macros/databarHistory.html`
- **Blocking I/O:** `get_recent_author(page)` — versions/DB lookup
- **Blocker:** All callers are in infogami vendor templates: `history.html` (via `xdiff`), `lib/view_head.html`, `lib/edit_head.html` (via type system). Cannot modify handlers.

#### Migration 14: `macros/PageList.html`
- **Blocking I/O:** `list_pages(path, limit, offset)` — DB query
- **Blocker:** Only caller is `notfound.html`, rendered by infogami's delegate system. Cannot modify handler.

#### Migration 15: `templates/covers/author_photo.html`
- **Blocking I/O:** `author.get_photo_aspect_ratio()` — HTTP to coverstore
- **Blocker:** Called from `authors/infobox.html`, which is rendered from `type/author/view.html` via infogami's type system. Cannot modify handler.

#### Migration 16: `templates/diff.html`
- **Blocking I/O:** `get_version(page.key, page.revision)` — DB query
- **Blocker:** Template is rendered by infogami's `xdiff` function (`vendor/infogami/infogami/utils/view.py`). The `get_version` call is inside a `$def display_revision(page)` within the template. Moving this requires modifying vendored infogami code.

### 🗑️ N/A (1)

#### Migration 13: `macros/OLID.html`
- **Blocking I/O:** `get_document(key)` + `edition.get_authors()` — DB lookups
- **Status:** **Unused macro.** No callers found in the codebase (only i18n translation references). No migration needed.

## Files Modified

| File | Change |
|------|--------|
| `openlibrary/plugins/admin/code.py` | Precompute stats + items for imports_by_date |
| `openlibrary/plugins/openlibrary/authors.py` | Precompute random_author_search results |
| `openlibrary/plugins/upstream/covers.py` | Precompute image.info() for saved cover |
| `openlibrary/plugins/upstream/mybooks.py` | Precompute reading_goals + meta_photo_url |
| `openlibrary/templates/account/mybooks.html` | Accept `current_goal` param |
| `openlibrary/templates/account/reading_log.html` | Accept `meta_photo_url` param |
| `openlibrary/templates/admin/imports_by_date.html` | Accept precomputed `summary`/`items` |
| `openlibrary/templates/admin/index.html` | Accept `admin_stats` param |
| `openlibrary/templates/authors/index.html` | Accept `results` param |
| `openlibrary/templates/covers/saved.html` | Accept `image_info` param |
| `openlibrary/templates/showia.html` | Accept `edition` param |
| `openlibrary/templates/showmarc.html` | Accept `edition` param |
| `openlibrary/views/loanstats.py` | Precompute admin_stats |
| `openlibrary/views/showmarc.py` | Precompute edition for breadcrumbs |

## Testing

- ✅ 1642 Python tests pass
- ✅ 432 FastAPI tests pass
- ✅ All pre-commit hooks pass (ruff check, ruff format, mypy, etc.)

## Recommendations for Future Work

1. **Infogami vendor modifications:** The 4 blocked migrations (databarHistory, PageList, author_photo, diff) require changes to `vendor/infogami/`. This should be coordinated with the infogami team or done as a separate project.

2. **RawQueryCarousel audit:** The `books_data` pre-fetch mechanism exists but only lazy carousels use it. Non-lazy callers (cached carousels, inline carousels) still call Solr in the template. A follow-up audit of non-lazy callers would complete this migration.

3. **OLID.html cleanup:** The OLID macro has no callers and can be deleted as dead code.
