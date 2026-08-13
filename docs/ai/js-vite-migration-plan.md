# JS Build Migration: Webpack → Vite (Plan)

Plan for replacing `webpack.config.js` with a Vite build for the JavaScript
entry points, applying the methodology (and avoiding the mistakes) of the CSS
migration. Companion doc: [`css.md`](css.md) (CSS conventions + build notes).

> **Status: executed.** This was the pre-migration plan; see
> [`js-vite-migration-progress.md`](js-vite-migration-progress.md) for how it
> actually went (several decisions changed during execution).

---

## 1. Goal

Build the same three JS bundles (`all.js`, `partnerLib.js`, `sw.js`) plus the
same lazy-loaded chunks with Vite — same URLs, same globals, same polyfill
coverage, same source maps, same license headers — and delete the webpack
config + its now-unused devDependencies.

The CSS migration proved this is achievable with **byte- or structural-parity
verification, native Vite mechanisms over custom machinery, and one
documented, guarded failure mode per risk**.

## 2. Why this is a bigger migration than CSS

| | CSS (done) | JS (this plan) |
|---|---|---|
| Entries | 17 static files | 3 entry points + ~14 async chunks |
| Output contract | urls passed through | globals, polyfills, runtime CSS injection, service worker |
| File size | ≤150 KB each | `all.js` ~2.0 MB raw / 155 KB gzip; `sw.js` ~432 KB |
| Behavioral surface | url rewriting | babel transpile, CJS interop, `$` globals, `import()` chunking |

The risk profile is different: the CSS work was mostly *what Vite does to
urls*; the JS work is mostly *what Vite does to semantics* (module wrapping,
polyfilling, script type, chunk splitting).

## 3. Current build anatomy (verified ✅)

### `webpack.config.js`

- **Entries:** `all` → `js/index.js`, `partnerLib` → `js/partner_ol_lib.js`,
  `sw` → `js/service-worker.js`.
- **babel-loader** on all `.js` (excl. node_modules); `.babelrc` is
  `@babel/preset-env` with `useBuiltIns: "usage"`, `corejs: 3` → **API
  polyfills** (not just syntax).
- **CSS rule:** `style-loader` + `css-loader(url:false)` — for
  `import '../../../../static/css/js-all.css'` in `index.js` → CSS is injected
  as a `<style>` element **at runtime**.
- **ProvidePlugin** `$` / `jQuery` → 30 files use bare `$(` with no import ✅.
- **Dynamic imports** with `/* webpackChunkName: "tabs" */` magic comments
  (tabs, autocomplete, user-website, merge, type-changer, signup, clampers,
  goodreads-import, ListViewBody, and others) → hashed named chunks.
- **Output:** entries `[name].js`, chunks `[name].[contenthash].js`,
  `publicPath: "/static/build/js/"`.
- **devtool `source-map`** — intentionally exposed for prod debugging.
- **performance** `maxAssetSize/maxEntrypointSize: 703 KB`, `hints: error` in
  prod (build *fails* on oversized assets).
- `bail: prod`; `FORCE_POLLING=true` → chokidar polling.

### Consumption contract (must not change)

- `footer.html` loads the site bundle:
  `<script src="$static_url('build/js/all.js')" type="text/javascript">` —
  a **classic script**, cache-busted by `static_url` (md5 query param), not by
  filename hash ✅.
- `/sw.js` is served raw from disk by `openlibrary/plugins/openlibrary/code.py`
  (`open("static/build/js/sw.js").read()`) and registered as a **classic
  script** (`navigator.serviceWorker.register('/sw.js')` in
  `service-worker-init.js`) ✅. It bundles `workbox-*` packages directly.
- `partnerLib.js` is **not referenced anywhere in the repo** ✅ — presumably
  embedded by external partners. Keep building it identically; confirm
  consumers exist (open question).
- `bundlesize.config.json` guards 14 JS outputs incl. `all.js` (155 KB gzip),
  `readinglog-stats.*.js` (137 KB), and every named async chunk ✅.
- `service-worker-matchers.test.js` asserts chunk URL shapes
  `/static/build/js/4290.a0ae80aacde14696d322.js` → keep `[name].[hash].js`
  chunk naming under `/static/build/js/` ✅.
- Makefile `js` target builds into `js_new/`, **prepends an AGPL
  `// @license magnet:` header to every output file**, then atomically swaps
  into `js/` ✅.

### In-repo Vite references to model from (✅)

- `vite-css.config.mjs` — mode gating, `clearScreen: false`, `build.watch`
  chokidar polling, and the `cssBuildMarker` plugin (the `generateBundle`
  pattern).
- `openlibrary/components/vite-lit.config.mjs` — `format: 'es'`,
  `target: ['es2019', 'safari13']`, terser, sourcemaps.
- `openlibrary/components/vite.config.mjs` — `@vitejs/plugin-vue`.

### Dead / unused (cleanup candidates)

- `vue.config.js` — an unreferenced vue-cli leftover ✅.
- `workbox-webpack-plugin` in devDependencies — not used by
  `webpack.config.js` ✅.

---

## 4. Methodology: the parity-first playbook (learned from CSS)

1. **Baseline first.** Capture the exact current contract *before* writing a
   line of config: filenames, sizes, first lines (license header), sourcemap
   presence, chunk list.
2. **Build the harness, then the config.** A script that diffs webpack vs Vite
   output structurally (file list, gzip sizes, header presence) makes every
   behavioral difference visible the moment it appears.
3. **Prefer native Vite mechanisms.** When a behavior differs, look for the
   documented Vite/rollup switch (like `publicDir` replacing the url hack)
   before writing a plugin. Plugins only when there is no native answer.
4. **Fix the source when the source is wrong.** The CSS migration moved invalid
   mid-file `@import`s instead of teaching the build to tolerate them. Same
   applies to code that leans on webpack-isms.
5. **One difference at a time, with a minimal repro.** Don't stack fixes;
   verify each against the harness.
6. **Guard regressions in CI, not in runtime code.** The stylelint
   `ol/import-at-top` rule now fails `npm run lint` if imports regress. For JS,
   the equivalent is `bundlesize` + a chunk-name/shape check (see §8).
7. **Document everything, and add a marker.** The CSS output now starts with
   `/* built by Vite 8.0.16 (vite-css.config.mjs) */`. Do the same for JS
   bundles so any deployed file is attributable at a glance.

---

## 5. Phase 0 — Exploration checklist (do before writing config)

- [ ] ⚠️ Snapshot current webpack prod build: `NODE_ENV=production npx webpack`
      into `/tmp/js_wp`; record every output filename, size, and first line.
- [ ] ⚠️ List all `import()` sites and **diff `webpackChunkName` comments
      against the imported filenames** — several deliberately differ
      (`user-website`→`edit.js`, `goodreads-import`→`goodreads_import.js`,
      `type-changer`→`type_changer.js`), which changes Rollup's chunk names
      and breaks `bundlesize` globs (see D5).
- [ ] ⚠️ Enumerate every bare-`$`/`jQuery` file (30 today) and every explicit
      jquery import, to size the ProvidePlugin replacement.
- [ ] ⚠️ Find all CSS imports inside JS (is `js-all.css` the only one?) and
      every `url()` inside them.
- [ ] ⚠️ Find webpack-specific source usage: `webpackChunkName` comments,
      `__webpack_public_path__`, `process.env.NODE_ENV` references,
      `require.context`, `import.meta` assumptions.
- [ ] ⚠️ Inventory CJS deps (jquery-ui, colorbox, slick-carousel, flot,
      datatables.net-dt, lodash, chart.js 2.x, prismjs, isbn3,
      lucene-query-parser, tesseract.js, tiptap) — which need interop care.
- [ ] ⚠️ Confirm `partnerLib.js` consumers (ask: who embeds it?).
- [ ] ⚠️ Decide the browser floor (see Decision D2).
- [ ] ⚠️ Confirm jest/eslint don't depend on webpack output (jest uses
      babel-jest directly — should be unaffected; verify by running them).

---

## 6. Migration phases

### Phase 1 — Spike: three entries with a working build

Write `vite-js.config.mjs` (name TBD) with:

- `build.rollupOptions.input` = the three entries (absolute paths).
- `output.entryFileNames: '[name].js'`, `chunkFileNames: '[name].[hash].js'`,
  `assetFileNames: '[name][extname]'`, `publicPath`-equivalent
  (`base: '/static/build/js/'` — verify it does not rewrite the runtime paths).
- `sourcemap: true` (parity with exposed maps).
- **`sw` entry:** `format: 'iife'` + `output.inlineDynamicImports: true`
  (classic-script service worker must stay one self-contained file — see D4).
- `minify: 'esbuild'` for prod, no minify in dev; gate on `mode` (CSS pattern).

Expected spike outputs: `all.js`, `partnerLib.js`, `sw.js` + named chunks.
Compare the chunk **name list** against webpack's — every name must match the
`bundlesize` globs and the SW matcher tests. Different hashes are fine; names
are the contract.

### Phase 2 — Behavioral parity (the decision table in §7)

Resolve each difference empirically, one at a time, against the harness.

### Phase 3 — Wiring: scripts, Makefile, watch

- `watch:js` → `vite build -c vite-js.config.mjs --watch --mode development`;
  keep `clearScreen: false` so it coexists with `watch:css` under
  `concurrently`.
- `watch-polling` → same `FORCE_POLLING` → `build.watch.chokidar.usePolling`
  pattern as the CSS config.
- Makefile `js` target → swap `npx webpack` for `npx vite build -c
  vite-js.config.mjs`; the **license-header loop stays as-is** (it is
  build-tool-agnostic shell). Optionally move it into `output.banner` (D8).
- `build-assets` / `build-assets:js` script names unchanged.

### Phase 4 — Verification (see §8) + a deploy cycle on testing

Merge only after: harness parity, `bundlesize`, jest, eslint, e2e, and a
manual smoke of the async-chunk pages on testing with the marker visible.

### Phase 5 — Cleanup

- Delete `webpack.config.js` (and the deleted-CSS-config precedent).
- Remove devDeps once confirmed unused: `webpack`, `webpack-cli`,
  `babel-loader`, `style-loader`, `css-loader` (⚠️ verify nothing else uses it),
  `workbox-webpack-plugin` (already unused), delete `vue.config.js`.
- Keep `@babel/preset-env` + `core-js` if polyfills move to explicit imports
  (D2); drop them if the floor is relaxed.
- Write the migration doc (mirror the CSS migration notes in `css.md`), add the JS marker
  (D11), update `docs/ai/README.md` if it references the webpack build.

---

## 7. Decision table — known behavioral differences

### D1. CSS-in-JS: `js-all.css` is injected at runtime today — **highest-impact difference**

- **Today:** `import '../../../../static/css/js-all.css'` → `style-loader`
  injects a `<style>` tag from JS.
- **Vite:** extracts it to a **separate `.css` asset** in the output dir and
  expects a `<link>` (Vite removes the import from the JS at build time).
  If nobody links it, the styles silently vanish.
- **Options:** (a) accept extraction — emit `js-all.css` and add a `<link>`
  in the layout (Vite-native, better cache behavior; **recommended**);
  (b) keep runtime injection with a small plugin (exact behavior parity, adds
  machinery); (c) stop importing it from JS and include it in the CSS build
  (`page-plain.css` / a new entry).
- **Note:** `js-all.css` uses `url:false` semantics already (root-absolute
  urls) — if it goes through Vite's CSS pipeline, apply the same
  `publicDir: '.'` escape hatch from the CSS config.
- **Load-timing tradeoff:** today the CSS is injected at runtime from a
  footer script (non-render-blocking). A `<link>` (option a) is
  render-blocking — *where* it goes (head vs footer) is a real decision, not
  an implementation detail.

### D2. Polyfills & browser floor — second-biggest decision

- **Today:** babel `preset-env` + `core-js` **usage-based polyfills** against a
  floor of `Android >= 5, Safari >= 11.1, iOS >= 11.3` (browserslist).
- **Vite:** esbuild transpiles **syntax only, no API polyfills**; default
  target is `baseline-widely-available` (~Safari 16).
- **Options:**
  - (a) **`@vitejs/plugin-legacy`** — generates modern + legacy bundles
    (polyfilled, `nomodule` fallback). Native, but the layout must serve two
    scripts and `static_url` must keep pointing at the modern file. Real
    template + caching work.
  - (b) **Explicit polyfill imports** — `import 'core-js/stable'` +
    `import 'regenerator-runtime/runtime'` at the top of `index.js` +
    `build.target` set to the legacy floor for syntax. Closest behavior to
    today with the least machinery; cost is polyfills-for-all instead of
    usage-based (bundle grows). **Recommended for a first cut.**
  - (c) **Relax the floor** to match the components builds' precedent
    (`es2019`/`safari13`) — simplest, but is a product decision (drops old
    Android/Safari). Components already made this trade; the whole site has
    not.
- ⚠️ Whatever is chosen must be validated by actually rendering on an old
  browser (or with `browserslist`-targeted transpile checks).
- ⚠️ Under option (b), the explicit `core-js`/`regenerator` imports also end
  up in `sw.js` (the service worker runs in the same old-browser surface);
  acceptable, but worth knowing.

### D3. `$` / `jQuery` globals (ProvidePlugin)

- 30 files rely on bare `$(` with no import ✅.
- **Vite answer:** `@rollup/plugin-inject` (inject `import $ from 'jquery'`
  into modules that reference it) for parity, or add explicit imports
  (long-term clean; 30 files to touch). Note `index.js` already does
  `import 'jquery'` and sets `window.$` / `window.jQuery` — the ProvidePlugin
  is about the *other* modules.
- Recommend: `@rollup/plugin-inject` now; explicit imports as a follow-up.

### D4. Service worker (`sw.js`) — keep it a self-contained classic script

- **Today:** single IIFE-ish file, all workbox bundled in, served raw at
  `/sw.js`, registered as classic ✅.
- **Vite danger:** default output is ESM with externalized chunk references.
  An ESM or chunk-splitting `sw.js` can break registration or first load.
- **Answer:** `format: 'iife'` + `inlineDynamicImports: true` (and/or a
  dedicated mini-config for `sw`). Verify no `import` statements remain in
  `sw.js` and no `[name].[hash].js` dependencies. ⚠️ Confirm the SW doesn't
  share modules with `all.js` that would force Rollup to split them out (it
  shouldn't — workbox is only imported by the SW).
- ⚠️ Also verify the SW **matcher tests** still pass (they assert URL shapes).

### D5. Chunk naming vs `bundlesize` and SW matchers — **known trap**

Rollup names dynamic-import chunks after the **imported filename**, while
webpack honors the `webpackChunkName` magic comment. These **deliberately
differ today**, so chunk names would silently change:

| `import()` in index.js | file | webpack chunk | Rollup would emit |
|---|---|---|---|
| `webpackChunkName: "user-website"` | `edit.js` | `user-website.<hash>.js` | `edit-<hash>.js` ❌ glob `user-website.*.js` stops matching |
| `webpackChunkName: "goodreads-import"` | `goodreads_import.js` | `goodreads-import.<hash>.js` | `goodreads_import-<hash>.js` ❌ |
| `webpackChunkName: "type-changer"` | `type_changer.js` | `type-changer.<hash>.js` | `type_changer-<hash>.js` ❌ |
| `webpackChunkName: "tabs"` (etc.) | `tabs.js` | matches | matches ✅ |

`bundlesize` globs and the SW matcher whitelist are keyed on the *webpack*
names, so those three chunks would silently escape their size gates. Plan for
one of: a chunk-name mapping (`chunkFileNames` can't remap per-import, so use
`output.manualChunks` or rename the source files to match), or update the
`bundlesize` globs to the new names. Add a harness check that asserts every
emitted chunk name matches a `bundlesize` glob (a missing glob fails CI).

`chunkFileNames: '[name].[hash].js'` keeps the URL *shape* stable; the base
names are the contract that needs the above audit.

### D6. Source maps (exposed in prod)

- Vite `build.sourcemap: true` produces `.map` files next to outputs; names
  will be `<entry>.js.map` — the same contract (nginx serves `static/build/**`)
  ✅. ⚠️ Confirm nothing asserts map filenames, and decide whether `sw.js.map`
  should be excluded (webpack currently emits it too — parity says keep).

### D7. Performance limits (webpack fails >703 KB; Vite only warns)

- Vite warns at `chunkSizeWarningLimit` (default 500 KB) but **cannot fail the
  build**. `all.js` (2 MB raw / 155 KB gzip) would warn loudly.
- **Answer:** set `chunkSizeWarningLimit` high enough to keep the build quiet
  (or accept the warnings) and let the existing **`bundlesize` CI gate** be
  the enforcement — it already fails PRs. Document this as the deliberate
  replacement for `performance.hints: 'error'`.

### D8. AGPL license header

- Currently a Makefile shell loop over every output file ✅. It is
  build-agnostic and will keep working untouched.
- Optionally fold into Vite via `output.banner` — note that **for JS, rollup's
  `banner` works natively** (it was only CSS assets that needed the
  `generateBundle` plugin). Either approach is fine; don't double-add.

### D9. `NODE_ENV` vs Vite `mode`

- Webpack keys off `NODE_ENV`; the CSS config already gates on `mode`
  (`production` default, `--mode development` for watch). Mirror that — it
  makes `make js` deterministic regardless of the shell environment.
- ⚠️ Check `process.env.NODE_ENV` references in JS source; Vite replaces
  `process.env.NODE_ENV` at build time, but other env vars used in source
  would need `define`.

### D10. Watch / polling / shared terminal

- Copy the CSS pattern: `clearScreen: false`, `build.watch.chokidar`
  `usePolling` on `FORCE_POLLING`. Keep `watch:js` and `watch:css` streaming
  under `concurrently`.

### D11. Build-tool marker

- Add the `cssBuildMarker` equivalent for JS: prepend
  `/* built by Vite ${version} (vite-js.config.mjs) */` to every JS output.
  For chunks, `output.banner` works natively; for `sw.js` (IIFE) it applies
  too. Keeps deployed files attributable and gives a quick version check.

### D12. Legacy CJS deps interop

- jquery-ui, slick-carousel, flot, datatables, chart.js 2.x, prismjs, etc. are
  CJS/UMD. Vite's build pipeline (esbuild pre-bundling + rollup commonjs)
  usually interops fine, but expect a few `this`/`exports` quirks; `build.commonjsOptions`
  is the tuning knob if a lib misbehaves. ⚠️ Watch out for rollup
  tree-shaking dropping **side-effect-only imports** (jquery-ui, colorbox,
  slick are imported purely for their jQuery-plugin side effects) — verify
  with the global-contract harness check rather than assuming.
  ⚠️ Smoke-test the pages that exercise each: edit page (datatables/tiptap),
  search facets (flot/chart.js), carousels (slick), barcode (quagga), tesseract
  OCR, ISBN scanner (isbn3).

---

## 8. Verification matrix

### Parity harness (script, committed)

Compare `/tmp/js_wp` (webpack) vs `/tmp/js_vite` (Vite) on:

- [ ] Output **file name sets** are equal (entries + chunk base names; hashes
      differ, names must not).
- [ ] `gzip -c` sizes within a documented tolerance per file (raw will differ;
      catch anything >~10%).
- [ ] Every file starts with the AGPL license header (and, after D11, the
      marker on Vite output).
- [ ] `.map` files present for every output.
- [ ] `sw.js` contains **no `import`/`export`** statements and no chunk
      references.
- [ ] Globals contract: load `all.js` in a bare jsdom page; assert
      `window.$`, `window.jQuery`, and the `ol.*` globals from `exposeGlobally`
      exist (⚠️ derive the exact list from `jsdef.js`).

### Automated gates (CI)

- `bundlesize` (already in CI; unchanged paths) — catches bloat **and** missing
  chunks (glob won't match → failure).
- jest (babel-jest, tool-agnostic) — unchanged.
- eslint — unchanged.
- pre-commit — unchanged.
- Playwright e2e + a11y suites — unchanged; add one page to the parity harness
  if needed.

### Manual smoke (async-chunk pages)

Edit page (`user-website`, `autocomplete`, tiptap/datatables), search
(`search`, `graphs`, `carousel`), `/account/books/...` (`readinglog-stats`),
signup, merge, type-changer, lists (`ListViewBody`), covers, add-book,
modal-links, goodreads-import. Check devtools for 404 chunk requests and the
marker comment in the Sources tab.

---

## 9. Risks & open questions

| Risk | Likelihood | Mitigation |
|---|---|---|
| Polyfill gap breaks old browsers (D2) | High if skipped | Explicit `core-js`/regenerator imports or `plugin-legacy`; test on floor browsers |
| `js-all.css` silently missing (D1) | High if missed | Add `<link>`; the parity harness + visual check catches it |
| `sw.js` shape change breaks offline/PWA | Medium | IIFE + inline; verify no `import` statements; test offline in browser |
| Chunk names drift from bundlesize/SW-matcher expectations | Medium | Harness asserts name sets; `bundlesize` fails on missing globs |
| CJS dep interop quirks | Medium | Smoke-test per-library pages |
| Shared-chunk injection into `sw.js` | Low | Confirm workbox modules are SW-only; fail harness on chunk refs in `sw.js` |

**Open questions for the team:**
1. Browser floor: keep `Android >= 5`/`Safari 11.1` (D2a/D2b) or align with the
   components builds' `es2019`/`safari13` (D2c)?
2. `js-all.css`: extracted `<link>` (D1a) or keep runtime injection (D1b)?
3. Who consumes `partnerLib.js`? Can it move to ESM too, or must it stay a
   classic script?
4. Is the AGPL header still required via Makefile loop, or is moving to
   `output.banner` preferred (D8)?

---

## 10. Useful references

- `docs/ai/css.md` — the completed CSS migration (conventions + build notes,
  methodology, parity checks, marker).
- `vite-css.config.mjs` — mode gating, `clearScreen`, polling, marker plugin.
- `openlibrary/components/vite-lit.config.mjs` — ESM output, browser target,
  terser, sourcemaps.
- `openlibrary/components/vite.config.mjs` — Vue SFC handling.
- `bundlesize.config.json` — the JS size/chunk-name gate.
- `service-worker-matchers.test.js` — the chunk-URL shape assertions.
