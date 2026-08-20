# JS Build Migration: Webpack → Vite — Progress Log

Live working notes for executing [`js-vite-migration-plan.md`](js-vite-migration-plan.md).

> Status: **working build, verified in the real running app, cleaned up.** `make js`
> produces Vite-built `all.js` (a 1 KB facade), `sw.js`, `partnerLib.js` + ~55
> chunks. `webpack.config.js` and its devDeps are deleted. Verified with
> Playwright against the live dev site (localhost:8080) + the parity harness.

---

## 1. What works now

`make js` (2.1s, vs webpack ~6.5s) runs three Vite builds:

```
vite-js.config.mjs        -> all.js (1 KB facade) -> main.js (the app, ESM code-split) + ~55 chunks + CSS
vite-js-iife.config.mjs   -> sw.js   (IIFE classic script)
vite-js-iife.config.mjs   -> partnerLib.js (IIFE classic script)
```

Verified end-to-end:
- **All 55 webpack chunk names preserved** (`user-website`, `modal-links`,
  `readinglog-stats`, `goodreads-import`, …) so `bundlesize` globs keep matching.
- **`bundlesize` 24/24**; `main.*.js` (app) 85 KB gzip + `jquery` 30 KB (webpack's
  single `all.js` was 155 KB); total JS gzip **555 KB → 372 KB (−33%)**.
- **jest 554/554**, eslint + stylelint clean.
- **Real-app browser test** (Playwright vs localhost:8080): zero JS-build errors
  across `/`, search, subjects, login, people; `window.$`/`window.jQuery`/jsdef
  globals set; `js-all.css` + chunk CSS applied via injected `<link>`s; search
  modal opens and slick carousels advance. **This test caught three real bugs the
  earlier root-served mock missed — see "real-app bugs" below.**
- **`scripts/js-build-parity.sh` → "PARITY OK"** (entries, chunk names, license
  headers, sourcemaps, `sw.js` shape).
- `sw.js` is a self-contained IIFE (workbox 7.4.1 bundled, no `import`/`export`);
  8.7 KB gzip vs webpack 14.4 KB (workbox ESM tree-shakes better).

---

## 2. Decisions made (with rationale)

### D-format: `all.js` becomes `type="module"` (the plan missed this)
The plan only flagged `sw.js` for `format: 'iife'`, but **`all.js` is also a
classic script** with ~55 dynamic imports. Rollup/Vite **cannot** emit
`iife`/`umd` for a code-splitting build, so the choice was:
- switch `all.js` to ESM + `<script type="module">` (**chosen**), or
- `inlineDynamicImports` + IIFE (one ~2 MB file, kills lazy-loading — rejected).

`footer.html` already loads a `<script type="module">` (lit-components), so this
is consistent. Consequence: the browser floor rises to Safari 11.1 / iOS 11.3
(native `type=module` + dynamic import) — the `Android >= 5` (Chrome 37) tail is
dropped *regardless of polyfills*. The `target` is `['safari11.1','ios11.3']`
to match `package.json`'s browserslist (Chrome/Edge/Firefox are "last 3 years" =
116/117+, never constraining anything Safari 11.1 doesn't). An earlier draft
hardcoded `chrome61`/`edge16`/`firefox60`, which are *older* than the real floor
and forced unnecessary transpilation (e.g. optional catch binding).

**The entry is now a thin facade.** `all.js` is `main-entry.js`, which only does
`import('./index.js')` — the real app lives in the `main.*.js` chunk. Without
this, rolldown hoists modules shared with lazy chunks (utils.js, …) into the
entry; those chunks then `import … from "./all.js"`, and because the entry is
also loaded via `<script src="all.js?v=…">` — a *different URL* — the browser
keeps a second module instance and re-runs the entry's side effects
(`customElements.define()` → "ol-search-modal has already been used", double
analytics pageview). A side-effect-free facade makes re-importing the entry
harmless.

### D1: CSS-in-JS — 6 files, not just `js-all.css`
Six explicit CSS imports in JS + transitive `@import`s. Vite **extracts** them:
the *chunk* CSS (`carousel.css` / `Toast.css` / `modals.css` /
`editions-table.css` / `ile.css`) is injected as a `<link>` at runtime by Vite's
preload helper on dynamic import. The *entry* CSS (`js-all.css`) is the subtle
one: Vite extracts it to `all.css` but **nothing links it** (the preload helper
only fires for dynamic imports), so its styles silently vanish — a real
regression vs webpack, caught in the browser (`#colorbox` etc. missing).

`js-all.css`'s contract is "loads only if JS is enabled, **non-render-blocking**"
(per its own header comment), so a `<link>` in the layout would be wrong. With
the facade entry (above) the entry CSS needs no custom machinery: it lands in
the `main` chunk's preload map as `js.css` and Vite injects a
`<link rel="stylesheet">` when `all.js` dynamically imports `main` — JS-only and
non-render-blocking, exact `style-loader` semantics with zero plugins.
`publicDir: '.'` + `copyPublicDir: false` keeps root-absolute `url(/static/...)`
unprocessed — zero data URIs, zero emitted image assets.

Extracted CSS is emitted as `[name].[hash].css` (e.g. `carousel.Xk3f9a2b.css`):
`/static/build` is served with `expires max` and these files aren't routed
through `static_url()`'s `?v=` cache-buster, so an unhashed name would be cached
by browsers forever across deploys. Vite rewrites the injected `<link>` URLs to
match, so nothing else needs to know the hash.

### NEW: real-app bugs the browser caught
Earlier verification served the build at the site *root*, which masked three
issues that only show up at the real path `/static/build/js/`:
1. **Missing `base`** — chunk `<link>`s and dynamic imports resolved against `/`
   (Vite default), 404-ing every chunk (`/carousel.js` instead of
   `/static/build/js/carousel.js`). Fix: `base: '/static/build/js/'` (= webpack's
   `output.publicPath`). Only the ESM build needs it; IIFE entries don't split.
2. **Entry re-evaluated by lazy chunks** — see the facade note above.
3. **`?v=` cache-buster splits the entry into two module instances** — the
   script tag loads `all.js?v=hash`, lazy chunks import `./all.js` (no query) →
   separate module instance → double side effects. The facade keeps shared
   modules out of the entry, so no lazy chunk imports it.

### D2: Polyfills — curated, not `core-js/stable`
Vite lowers **syntax only** (Oxc). Measured: no polyfills 108 KB gzip;
`core-js/stable` **177 KB** (blows the 155 KB budget); **curated 118 KB** ✅.
Added to `index.js`: `core-js/es/array/flat-map`, `object/from-entries`,
`promise/finally`, `symbol/async-iterator` — exactly what babel
`useBuiltIns:'usage'` would have emitted for the ES2018+ APIs the code uses.
(`for await…of` lowers to a `Symbol.asyncIterator`-based helper — no regenerator
needed; that's a Babel-ism Oxc doesn't use.)

### D3: `$` / `jQuery` globals — codemodmed to explicit imports (plugin deleted)
Initially a tiny `transform` plugin (`ol-inject-jquery-globals`) injected
`import $/jQuery from 'jquery'` into modules using bare `$`. **Bugs the browser
caught:** (1) `import jQuery, $ from 'jquery'` is a syntax error (two statements
needed); (2) the "module declares its own `$`" guard must require a *standalone*
`$`, else `const $tabs` falsely suppressed injection. The regexes could also
false-positive on `$` in strings/regex literals and `jQuery` in comments,
injecting unused imports.

**Superseded:** an eslint `no-undef` scan (AST-based, immune to those
false-positives) found **31 source files + 4 test files** that genuinely
reference unbound `$`/`jQuery`; each now has an explicit
`import $ from 'jquery';` (index.js gets both `$` and `jQuery` — it sets
`window.$`/`window.jQuery`). The inject plugin was deleted, and `$`/`jQuery`
were removed from eslint's globals so unbound usage is a `no-undef` error
again.

### D4: `sw.js` — IIFE, one entry per invocation
Rolldown treats `format:'iife'` as `codeSplitting:false`, which only allows
**one** input → the IIFE config takes `IIFE_ENTRY=sw|partnerLib`, run twice. All
three builds use `emptyOutDir:false`; the Makefile owns cleanliness.

### D5: Chunk names — 16-name map, not the 3 the plan listed
Rolldown names chunks after the imported *file*, webpack after the
`webpackChunkName` comment. 16 mismatches (`edit→user-website`,
`modals→modal-links`, `readinglog_stats→readinglog-stats`, …), remapped via a
`chunkFileNames` function.

### NEW: jquery-ui AMD interop — explicit wrapper modules (plugin deleted)
jquery-ui 1.14 ships **UMD only**; its inter-module deps are AMD
`define(["jquery","../widget",…], factory)`. Vite has no AMD loader, so importing
`jquery-ui/ui/widgets/tabs` alone ran the UMD browser-globals branch
`factory(jQuery)` *without* `../widget` → **`$.widget is not a function`**.

**Superseded:** an earlier `jquery-ui-amd-deps` transform plugin regex-extracted
each file's AMD `define([...])` deps and injected side-effect `import`s. That
worked (per-widget tree-shaking restored: `tabs` 4 KB gzip, `autocomplete` 7 KB,
`dialog` 19 KB) but parsed another library's internals at build time — a
maintenance boundary. Post-review it was replaced by **four explicit wrapper
modules** (`openlibrary/plugins/openlibrary/js/jquery-ui-{tabs,dialog,autocomplete,sortable}.js`),
each listing its AMD deps in topological order as plain `import`s. The 7
importing files now import the wrapper for the widget they use; the plugin and
its regex were deleted. Per-widget tree-shaking is unchanged (autocomplete 22 KB
raw entry, covers 3 KB + 26 KB touch-punch, dialog 66 KB) and jquery-ui upgrades
that alter the AMD graph are caught by unit tests that verify each wrapper
against the installed package (tests/unit/js/vite-js-plugins.test.js).

(The even earlier hand-rolled `jquery-ui.js` bootstrap forced a 79 KB shared
chunk onto every widget page — the wrappers avoid that by importing only each
widget's own closure.)

### D7: bundlesize limits recalibrated
Rolldown inlines per-chunk deps; webpack hid shared deps in a giant 133 KB gzip
vendor chunk. Per-chunk gzip grew even though total fell −33%. Updated:
`graphs` 19→23 KB, `carousel` 6→13 KB, `editions-table` 33→35 KB.

### D8: AGPL license header — moved into the Vite configs
Both configs apply the LibreJS magnet comment via `output.postBanner`
(`AGPL_LICENSE_HEADER`) + `output.postFooter` (`// @license-end`), shared from
`vite-js-shared.mjs`. Applied after minification so the comments survive;
rolldown-vite ignores `output.banner`, `postBanner` is the supported
alternative. The Makefile's post-build shell loop was deleted (it duplicated
this). No build-tool marker is emitted (dropped post-review).

---

## 3. Where things got stuck / gotchas learned

1. **`$` can't be a second default import** — `import jQuery, $ from 'jquery'`
   is a syntax error; must be two statements.
2. **Path guard `id.includes('/openlibrary/')` matches `node_modules`** because
   the project root dir is literally `openlibrary` — guard on `node_modules`.
3. **`const $tabs` is not a `$` declaration** — regex guard needs standalone `$`.
4. **IIFE = single input** in rolldown (not just "no code splitting").
5. **`output.banner` is ignored** by rolldown-vite → use `output.postBanner`
   (applied after minification) instead of a `generateBundle` plugin.
6. **LightningCSS (Vite 8 default) rejects IE star-hacks** the JS-imported CSS
   had but the CSS build never touched (removed from `legacy-datatables.css`).
7. **`regenerator-runtime` isn't a dep and isn't needed** — Oxc uses its own
   helpers.
8. **`npm uninstall workbox-webpack-plugin` would delete the workbox packages
   `sw.js` imports directly** (they were only transitive) — promoted the 6
   `workbox-*` packages to direct devDeps before removing it.
9. **Rebuilding webpack for the parity harness** — `webpack.config.js` is deleted,
   so `scripts/js-build-parity.sh` installs webpack+loaders into a throwaway
   `mktemp -d` prefix and wraps the git-recovered config: `resolveLoader.modules`
   → the prefix (webpack resolves loaders from `context`, ignoring `NODE_PATH`),
   and `NODE_PATH` → the prefix (the config itself `require("webpack")`).
10. **Vite `base` defaults to `/`** — chunks 404 unless `base` matches the real
    public path (`/static/build/js/`). A root-served mock hides this; the real
    app caught it immediately.
11. **`?v=` cache-buster splits the entry into two module instances** — the
    script tag (`all.js?v=…`) and a lazy chunk's `import "./all.js"` are
different URLs → entry side effects run twice. Fixed with the facade entry.

### Pre-existing source issues surfaced (not introduced)
- `cbox.css` references `static/images/icons/icon_close-pop.png`, which **does
  not exist** in the repo (404 today too; Vite now warns at build time).
- `ol.analytics.js` calls `window.archive_analytics.send_pageview()` unguarded on
  DOMContentLoaded (throws if athena.js is blocked).

---

## 4. Files changed

**Deleted:** `webpack.config.js`, `vue.config.js`

**New:** `vite-js.config.mjs`, `vite-js-iife.config.mjs`, `main-entry.js`,
`scripts/js-build-parity.sh`, and (post-review) `vite-js-shared.mjs` (shared
build options + AGPL license constants) + `vite-js-plugins.mjs` (transform
plugins + chunk names, unit-tested in `tests/unit/js/vite-js-plugins.test.js`)

**Edited:**
- `Makefile` — `js` target: three Vite builds (license loop removed; the Vite
  configs now emit the AGPL header/footer)
- `package.json` — `watch:js` runs the three configs under `concurrently`;
  removed `webpack`, `webpack-cli`, `babel-loader`, `style-loader`, `css-loader`,
  `workbox-webpack-plugin`; added 6 direct `workbox-*` deps (+ lockfile)
- `eslint.config.cjs` — removed the deleted `webpack.config.js`/`vue.config.js`
- `openlibrary/templates/site/footer.html` — `all.js` → `type="module"`
- `openlibrary/plugins/openlibrary/js/index.js` — 4 curated core-js imports
- `static/css/legacy-datatables.css` — removed 2 dead IE star-hacks
- `bundlesize.config.json` — 3 limits recalibrated; `all.js` → `main.*.js`
- `docs/ai/README.md` — JS build section now describes the Vite toolchain
- `docs/ai/js-vite-migration-plan.md` + this file — the migration plan/progress
  record (the CSS migration notes live in `docs/ai/css.md`; the old
  `css-vite-migration.md` companion doc was never created on this branch)

---

## 5. Open questions for the team

1. **Browser floor** — ESM raises it to ~Chrome 61/Safari 11; drop `Android 5`
   formally, or add `@vitejs/plugin-legacy` for a `nomodule` fallback?
2. **`partnerLib.js`** — now 0.7 KB gzip (webpack's 19 KB was mostly polyfills
   for Android 5). Who embeds it, and do they need the old-browser polyfills?
3. ~~**`js-all.css` load timing**~~ — **resolved**: injected as a `<link>` by
   the facade's preload when `main` loads (JS-only, non-render-blocking).
4. **Deploy smoke** — run the async-chunk pages (edit, search, lists, add-book)
   on `testing` before merge.
