# jQuery usage inventory

> Snapshot of every place Open Library's frontend uses jQuery, taken after the
> Vite migration made all jQuery usage **explicit** (every file that touches
> `$`/`jQuery` has a real `import $ from 'jquery';`, and eslint `no-undef`
> errors on any unbound use). The point of this doc is to make the migration
> surface legible: nothing here is hidden behind build-time magic anymore.
>
> Generated August 2026. Regenerate with:
> `grep -rln "from 'jquery'" openlibrary/plugins/openlibrary/js/ tests/unit/js/`

## Bottom line

- **33 source files** import jQuery directly (39 including the 6 test/setup files).
- **8 files** use `$.ajax`-family networking (→ `fetch` is the natural replacement).
- **7 files** depend on **jquery-ui widgets** (`dialog`, `tabs`, `autocomplete`,
  `sortable`) — the biggest single line item, and the one with no one-to-one
  vanilla replacement.
- **6 files** call the **jquery-colorbox** lightbox; **1 file** defines a plugin
  (`jquery.repeat.js`).
- jQuery is loaded once and shared: a single `jquery.sWDz-tAd.js` chunk
  (~85 KB raw / ~31 KB gzip) plus jquery-ui wrappers
  (`jquery-ui-{tabs,dialog,autocomplete,sortable}.js`).

## jQuery-ecosystem dependencies (package.json)

| Package | Version | Used for |
|---|---|---|
| `jquery` | 3.7.1 | the library itself |
| `jquery-ui` | 1.14.2 | dialog, tabs, autocomplete, sortable widgets |
| `jquery-colorbox` | 1.6.4 | lightbox (`.colorbox()`) |
| `jquery-ui-touch-punch` | 0.2.3 | touch support for sortable |
| `slick-carousel` | 1.6.0 | carousel (bundles its own jQuery dep) |
| `datatables.net-dt` | 1.13.11 | editions table (requires jQuery) |

jquery-ui is bootstrapped by four explicit wrapper modules that list its AMD
deps in dependency order — see
`openlibrary/plugins/openlibrary/js/jquery-ui-{tabs,dialog,autocomplete,sortable}.js`
and `tests/unit/js/vite-js-plugins.test.js` (which verifies the wrappers stay in
sync with the installed package).

## Source files importing jQuery (33)

Usage categories: **ajax** (`$.ajax`/`$.post`), **ui** (jquery-ui widgets),
**colorbox** (`.colorbox()`), **plugin** (defines a `$.fn` plugin), **events**
(`.on`/`.click`/etc.), **dom** (selection/manipulation), **utils** (`$.extend`,
`$.each`, `$.Deferred`, …).

### AJAX — 8 files

| File | Calls | Notes |
|---|---|---|
| `admin.js` | `$.post` | |
| `autocomplete.js` | `$.ajax` | also jquery-ui autocomplete |
| `carousel/Carousel.js` | `$.ajax` | |
| `goodreads_import.js` | `$.ajax` | |
| `lists/ListViewBody.js` | `$.ajax`, `$.post` | also jquery-ui dialog |
| `merge.js` | `$.ajax` | also jquery-ui dialog |
| `modals/index.js` | `$.ajax` | also colorbox |
| `signup.js` | `$.ajax` | |

### jquery-ui widgets — 7 files

| File | Widgets |
|---|---|
| `autocomplete.js` | autocomplete + sortable |
| `covers.js` | sortable + disable-selection |
| `dialog.js` | dialog |
| `lists/ListViewBody.js` | dialog |
| `merge.js` | dialog |
| `waitlist.js` | dialog |
| `tabs.js` | tabs |

These are the hardest to migrate: replacing them means native `<dialog>`,
custom combobox/autocomplete, and HTML5 drag-and-drop.

### jquery-colorbox — 6 files

`dialog.js`, `my-books/CreateListForm.js`, `my-books/MyBooksDropper/CheckInComponents.js`,
`my-books/MyBooksDropper/ReadingLists.js`, `modals/index.js` (via `$.colorbox`).
`utils.js` also calls `parent.jQuery.fn.colorbox.close()` — but on the *parent
window's* global (lightbox opened in an iframe), so it doesn't import jQuery
itself.

### Plugin definition — 1 file

| File | Defines |
|---|---|
| `jquery.repeat.js` | `$.fn.repeat` (form-field repetition) — also uses `$.extend`, `$.Deferred` |

### Everything else — DOM/events only (~19 files)

`add-book.js`, `carousel/index.js`, `compact-title/index.js`, `dropper/Dropper.js`,
`dropper/index.js`, `edit.js`, `editions-table/index.js` (DataTables),
`graphs/plot.js`, `ile/index.js`, `ile/utils/SelectionManager/SelectionManager.js`,
`index.js` (also sets the globals, below), `lazy-thing-preview.js`,
`offline-banner.js`, `ol.analytics.js`, `ol.js`, `readinglog_stats.js`,
`search.js`, `Toast.js`.

These are mostly `$(selector)` + `.on()`/`.click()` + `.addClass`/`.html` — the
long tail of mechanical rewrites to `querySelector`/`addEventListener`.

## Global escape hatches (delete last)

- `openlibrary/plugins/openlibrary/js/index.js:23-24` — `window.jQuery = jQuery;
  window.$ = jQuery;`. Exists for legacy inline scripts and the jquery-ui UMD
  globals branch. Must stay until those consumers are gone.
- `tests/unit/js/setup.js` — makes `$`/`jQuery` window globals for jest tests.

## Test files importing jQuery (5 + setup)

`carousel.test.js`, `droppers.test.js`, `editionEditPageClassification.test.js`,
`editionsEditPage.test.js`, `jquery.repeat.test.js`, plus `setup.js` (which
provides the `$`/`jQuery` window globals for jest). These mirror the source
modules under test.

## Migration notes

1. **Start with AJAX** — 8 files, mechanical `$.ajax` → `fetch`, high value,
   zero UI risk.
2. **jquery-ui is the critical path** — audit whether `dialog`/`tabs`/
   `autocomplete`/`sortable` are used on pages that could adopt native
   alternatives incrementally; the wrapper modules make the dependency graph
   explicit and testable.
3. **`window.$`/`window.jQuery` are the finish line** — when the last file
   drops its import, remove the globals and the `jquery` entry from the build.
4. eslint guards the surface: unbound `$`/`jQuery` is a `no-undef` error, so
   this inventory can only shrink.
