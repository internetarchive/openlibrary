# CSS Build: Webpack → Vite Migration

Notes from replacing `webpack.config.css.js` with a Vite build for the CSS
entry points (`tokens`, `ol-components`, `page-*.css`).

## Status: done (wired into the build)

`vite-css.config.mjs` compiles the same 17 entries with `@import` resolution and
esbuild minification. (No stub-JS cleanup is needed: Vite 8 omits the empty JS
chunk for pure-CSS entries natively — earlier webpack needed
RemoveJSAssetsPlugin for the same quirk.) The `css` Make target, `watch:css`,
`watch`, and `watch-polling` now use Vite. `webpack.config.css.js` is deleted;
`mini-css-extract-plugin`, `css-minimizer-webpack-plugin`, and `glob` were
removed from devDependencies (`css-loader` stays — the JS webpack config still
uses it).

## Key findings

### Mid-file `@import` is invalid CSS

Vite silently drops `@import` statements that appear after other content;
webpack's css-loader hoists and processes them anyway. Fixed by moving every
mid-file `@import` to the top of the file:

- `static/css/legacy.css` (41 imports — the big one)
- `static/css/page-admin.css`, `page-book.css`, `page-design.css`,
  `page-plain.css`, `page-signup.css`, `page-user.css`

Import-only comments (e.g. `/* SITE DEFAULTS */`, `/* FOOTER */`) were moved up
with their import groups; section-header comments that head rules below them
(e.g. `/* TYPOGRAPHY */`) were left in place. The full comment set is unchanged.

**Zero risk:** after the moves, the webpack build output was **byte-identical**
to before (all 17 files), so cascade order is unchanged.

### Enforced by lint

A repo-local stylelint rule `ol/import-at-top`
(`stylelint/ol-import-at-top.mjs`, registered in `.stylelintrc.json`) flags any
`@import` after the first statement, so a regression here fails `npm run lint`
(CI), the pre-commit stylelint hook, and editor linting — not just the build.
`@charset` and blockless `@layer` statements may still precede imports per spec;
imports nested inside rules/media are always flagged.

### `url()` passthrough (webpack `url:false` parity)

Vite inlines small `/static/images/...` assets as base64 data URIs by default,
which roughly **doubles** gzip size on image-heavy pages and would fail the
`bundlesize` CI check. Solved with a PostCSS plugin that runs in the `Once`
phase and encodes each root-absolute `url(/static/...)` as
`url(#__OL__/static/...)`; a `closeBundle` hook decodes the placeholders in the
emitted files.

- **Gotcha discovered while debugging:** a PostCSS plugin using the
  `Declaration` visitor runs *after* Vite's internal url-rewriting plugin
  (`UrlRewritePostcssPlugin`, which also runs in `Once`) and sees nothing left
  to encode. `Once` runs right after postcss-import inlines the raw imported
  CSS but *before* the url rewrite, so it sees everything.
- The `#` prefix works because Vite's url processing skips fragment-style urls.
- This relies on Vite-internal ordering, so `closeBundle` also scans the output
  for undecoded `#__OL__` placeholders or stray JS chunks (**fails the build**)
  and leaked `data:image/` URIs (warns — `bundlesize` CI catches inline bloat,
  and the source may intentionally use data URIs, which Vite passes through)
  if a future Vite upgrade breaks the mechanism.

### `@charset` handling

`legacy.css` used to declare `@charset "utf-8";` at the top; webpack's
css-loader hoisted it into every output whose entry imported legacy.css (7 of
17). postcss-import strips `@charset` from inlined files (and warns when one
sits anywhere but the very first statement), so the declaration was simply
removed from `legacy.css` — this silences the 7 "`@charset` must precede all
other statements" warnings, and the output simply lacks the declaration.
`@charset "utf-8";` is semantically meaningless for HTTP-served CSS (the
charset comes from HTTP headers; utf-8 is the default), so this is not a
functional loss — just a ~16-byte-per-file diff vs webpack's output on the 7
legacy-importing files.

### Minor output diffs vs webpack

- The 7 legacy-importing outputs no longer start with `@charset "utf-8";`
  (see above).
- `NODE_ENV` gating: `make css` sets `NODE_ENV=production` explicitly so
  production output is always minified regardless of the shell environment;
  `watch:css` uses `NODE_ENV=development` for readable unminified output
  (matches the old webpack dev behavior).

## Speed

CSS-only build (17 entries, minified), median of 4 runs on an 8-core Mac:

| Environment | webpack | Vite | Speedup |
|---|---|---|---|
| Host | ~2.45s | ~0.66s | ~3.7× |
| Docker (`docker compose run`, incl. ~1s container startup) | ~4.9s | ~2.3s | ~2.1× |
| Docker (pure build, minus startup) | ~4.0s | ~1.4s | ~2.9× |

Raw runs: host webpack 2.73/2.39/2.44/2.45; host vite 0.65/0.66/0.66/0.67;
docker webpack 5.10/4.88/4.41/5.03; docker vite 2.42/2.15/2.23/2.40. Docker
container startup (no-op `echo`) measured ~0.95s — the per-run `docker compose
run` overhead is bigger than Vite's entire host build, so keeping a warm
container (`docker compose exec`) matters for the dev loop.

## Output size & parity (vite vs webpack, both minified)

- **`/static/` reference counts match exactly** per file (e.g. page-admin 35/35,
  page-edit 36/36, page-form 38/38, page-plain 39/39, page-user 39/39,
  page-lists 40/40, page-book 15/15).
- **`url()` content sets are identical** (`comm` diff empty).
- **Zero data URIs, zero emitted assets, zero leftover placeholders.**
- **Selector parity ~100%** (no missing selectors vs webpack output).
- **Raw sizes within ~0.2–1%** (esbuild vs cssnano minifier variance):

  | File | webpack bytes | vite bytes |
  |---|---|---|
  | page-admin | 148,907 | 148,631 |
  | page-book | 91,229 | 90,252 |
  | page-edit | 145,894 | 145,585 |
  | page-form | 146,249 | 145,933 |
  | page-plain | 146,319 | 146,000 |
  | page-user | 162,426 | 162,136 |

- **Gzip within 1KB** of webpack on every file (most identical, e.g. page-admin
  27KB/27KB, page-edit 26KB/26KB, page-user 29KB/29KB; a few 1KB smaller, e.g.
  page-form 27→26KB, page-lists 30→29KB, page-subject 9→8KB). All files remain
  under their `bundlesize.config.json` limits (24/24 checks pass).

## How the byte-by-byte comparison works

The **byte-identical** claim applies to the *webpack-before vs webpack-after*
safety check on the import hoisting: the rebuilt output matched the pre-edit
production build exactly (`cmp` passed, sizes identical to the byte), proving
the source reordering changed nothing.

Webpack vs Vite outputs are *not* byte-identical (different minifiers), so
parity is verified structurally. Reproduce either check like this (the webpack
CSS config is deleted from the repo — recover it from git):

```bash
# webpack output
git show HEAD:webpack.config.css.js > /tmp/wp.css.js
mkdir -p /tmp/css_wp /tmp/css_vite
BUILD_DIR=/tmp/css_wp NODE_ENV=production npx webpack --config /tmp/wp.css.js

# vite output
BUILD_DIR=/tmp/css_vite npx vite build -c vite-css.config.mjs

# 1. byte-level compare
for f in /tmp/css_wp/*.css; do
  name=$(basename "$f")
  cmp -s "$f" "/tmp/css_vite/$name" && echo "$name: IDENTICAL" || echo "$name: DIFFERS"
done

# 2. url() reference parity (should be empty both directions)
comm -3 <(grep -oE 'url\([^)]*\)' /tmp/css_wp/page-admin.css | sort -u) \
        <(grep -oE 'url\([^)]*\)' /tmp/css_vite/page-admin.css | sort -u)

# 3. /static/ reference counts (must match per file)
for f in /tmp/css_wp/*.css; do
  name=$(basename "$f")
  echo "$name wp=$(grep -o '/static/' "$f" | wc -l) vite=$(grep -o '/static/' "/tmp/css_vite/$name" | wc -l)"
done

# 4. gzip sizes (should be within 1KB)
gzip -c /tmp/css_wp/page-admin.css | wc -c
gzip -c /tmp/css_vite/page-admin.css | wc -c

# 5. selector parity (vite selectors missing from webpack output — expect none)
comm -23 <(grep -oE '\.[a-zA-Z][a-zA-Z0-9_-]*' /tmp/css_wp/page-admin.css | sort -u) \
         <(grep -oE '\.[a-zA-Z][a-zA-Z0-9_-]*' /tmp/css_vite/page-admin.css | sort -u)
```

## Watch / polling

- `npm run watch` runs `concurrently` over `watch:js` (webpack) and `watch:css`
  (Vite).
- `watch-polling` sets `FORCE_POLLING=true`; the Vite config responds by
  enabling chokidar polling in `build.watch` for docker bind-mount
  environments. Note `FORCE_POLLING` implies watch mode, which is exactly what
  the `watch-polling` script is for.

## Remaining work

- Visual/acceptance check of a few pages comparing webpack vs Vite output.
