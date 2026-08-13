# Code Quality Review Findings — `feat(js): migrate JS build from webpack to Vite`

Working list derived from the thermo-nuclear code quality review of commit
`d72666ec8` (JS build migration: webpack → Vite). Check items off as they're
fixed; add notes under each finding as work progresses.

---

## 1. [Blocker] Parity harness is dead on arrival — `git show HEAD:webpack.config.js` fails

- [x] **Fix** — done

`scripts/js-build-parity.sh` started with:

```bash
git show HEAD:webpack.config.js > "$WP_CONFIG"
```

but this commit deletes `webpack.config.js`, so at HEAD the file doesn't exist
(`fatal: path 'webpack.config.js' does not exist in 'HEAD'`). Under
`set -euo pipefail` the script aborted on its first command.

**Fix applied:** the script now resolves the most recent ref that still
contains `webpack.config.js` via `git log --all --follow` (walking the list and
picking the first ref where `git cat-file -e "$r:webpack.config.js"` succeeds),
overridable with `WP_GIT_REF` or a third positional arg. Verified:
`bash scripts/js-build-parity.sh` → **PARITY OK** (full webpack + Vite rebuild,
all checks green).

**Notes:**
- First attempt used `git log --all --follow | head -n1`, which resolves to the
  *deletion* commit itself — fixed by walking the list until the file exists.


---

## 2. [High] Two new Vite configs, one duplicated body

- [x] **Fix** — done

`vite-js.config.mjs` and `vite-js-iife.config.mjs` duplicated nearly everything:
`outDir`, `forcePolling`, `VITE_VERSION`, `publicDir`, `clearScreen`,
`emptyOutDir`, `copyPublicDir`, `sourcemap`, `minify`, `target`,
`chunkSizeWarningLimit`, `watch` — and `jsBuildMarker()` verbatim (only the
config filename embedded in the marker string differed).

**Fix applied:** new `vite-js-shared.mjs` exports `VITE_VERSION`,
`jsBuildMarker(configFile)` (parameterized marker string), and
`commonBuildOptions({ mode })`. Both configs now only state what differs
(`base`, `input`, `output.format`, plugins). The IIFE config dropped from 78
lines to ~35. Also added all three JS vite configs to the eslint "Vite config
files" block so the shared module is linted (it wasn't covered by `*.config.mjs`
ignore).

**Notes:**
- Verified: all three `vite build` invocations succeed and
  `scripts/js-build-parity.sh` → **PARITY OK** with the refactored configs.
- `vite-js.config.mjs`/`vite-js-iife.config.mjs` are still ignored by eslint's
  `*.config.mjs` global ignore (pre-existing; same as `vite-css.config.mjs`).
-

---

## 3. [High] `VITE_VERSION` magic constant with a "keep in sync" comment

- [x] **Fix** — done

Two copies of `'8.0.16'`, each with `// keep in sync with package.json` — but
package.json declares `"vite": "^8.0.5"` (a range). The marker's purpose is to
record which version produced the file; hardcoding it guarantees it eventually
lies.

**Fix applied:** `vite-js-shared.mjs` now reads the installed version directly:

```js
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
export const VITE_VERSION = require('vite/package.json').version;
```

Constant deleted from both configs. Verified: marker still prints
`/* built by Vite 8.0.16 (…) */` (the installed version).

**Notes:**
-

---

## 4. [Medium-High] 58 dead `webpackChunkName` comments left in the source

- [x] **Fix** — done

`index.js` (plus `book-page-lists.js`, `design-system/index.js`) carried 58
`/* webpackChunkName: "user-website" */`-style magic comments. Vite/rolldown
ignores them — the real mapping is `CHUNK_NAME_MAP` in
`vite-js.config.mjs`, keyed off the imported *filename*, not the comment.

**Fix applied:** removed all 58 comments from `index.js` plus the ones in
`book-page-lists.js` and `design-system/index.js` (0 remain). Normalized the two
`import (` -> `import(` stragglers left behind. eslint clean on all three files;
`scripts/js-build-parity.sh` → **PARITY OK** (proves chunk names are driven by
`CHUNK_NAME_MAP`, not the dead comments).

**Notes:**
- One source of truth for chunk names now: `CHUNK_NAME_MAP` in
  `vite-js.config.mjs`.
-

---

## 5. [Medium] Regex source-mutation plugins are the least-tested magic here

- [x] **Add unit tests for the two transform plugins** — done
- [x] **Replace `injectJqueryGlobals` with explicit `import $ from 'jquery'`** — done
- [x] **Replace `jqueryUiAmdDeps` with explicit wrapper modules** — done

`injectJqueryGlobals` and `jqueryUiAmdDeps` parse and rewrite JS with regexes.
The plan (D3) recommended `@rollup/plugin-inject`; the custom plugin is
defensible (more surgical than plugin-inject, browser run caught real bugs), but
there was **zero unit coverage** for either transform, and the regexes can
false-positive: `(?<![\w$])\$(?![\w${])` matches `$` inside strings/comments,
injecting an unused `import $ from 'jquery'` into modules that don't need it.

**Fix applied (round 1):** both plugins + `chunkName`/`CHUNK_NAME_MAP` were
extracted from `vite-js.config.mjs` into a new importable `vite-js-plugins.mjs`
(config now imports from it). New `tests/unit/js/vite-js-plugins.test.js`
covered: `$`/`jQuery` injection, both-names case, already-imports guard,
self-declared-`$` guard, `$foo` non-match, node_modules skip, no-usage skip; AMD
dep injection order, jquery exclusion, non-jquery-ui skip, no-define skip;
chunk-name remapping, `main` special case, basename fallback. **16/16 pass.**

To import the repo-root `.mjs` from jest, added a `moduleNameMapper` entry for
`vite-js-plugins.mjs` and widened the jest transform regex to cover `.mjs`.
Also registered `vite-js-plugins.mjs` in eslint's Vite-config block.

**Fix applied (round 2 — the codemod):** the injection was replaced with
one-time explicit imports. An eslint `no-undef` scan (AST-based, immune to the
regex false-positives) found **31 source files + 4 test files** genuinely
reference unbound `$`/`jQuery` — not the ~30/14 the regexes suggested, and the
regexes were in fact injecting unused imports into 5 files (SearchModal's
`/[.…。]+$/` regex literal, `jQuery` in comments in Dropper/nonjquery_utils,
etc.). Each file now has `import $ from 'jquery';` (index.js gets both `$` and
`jQuery`). `injectJqueryGlobals()` was deleted from `vite-js-plugins.mjs` and
its tests removed. `$`/`jQuery` were removed from eslint's globals so unbound
usage is a hard `no-undef` error again. **PARITY OK; jest 575/575; lint clean.**

**Fix applied (round 3 — jquery-ui AMD):** `jqueryUiAmdDeps` was also deleted.
Its regex parsed another library's UMD wrapper at build time — a maintenance
boundary. Replaced by **four explicit wrapper modules**
(`openlibrary/plugins/openlibrary/js/jquery-ui-{tabs,dialog,autocomplete,sortable}.js`),
each listing its AMD `define([...])` deps in topological order as plain
`import`s; the 7 importing files now import the wrapper for the widget they
use. Per-widget tree-shaking is unchanged (verified: autocomplete 22 KB entry,
covers 3 KB + 26 KB touch-punch, dialog 66 KB — identical to the plugin era).
New tests verify each wrapper against the installed jquery-ui package (files
exist + valid topo order + dialog closure completeness), so a jquery-ui upgrade
that changes the AMD graph fails loudly instead of breaking at runtime.

**Notes:**
- An earlier hand-rolled `jquery-ui.js` bootstrap forced a 79 KB shared chunk
  onto every widget page; the per-widget wrappers avoid that by importing only
  each widget's own closure.
-

---

## 6. [Medium] Doc inaccuracies in the committed docs

- [x] **Fix** — done

- Progress doc's "Files changed" claimed `docs/ai/css-vite-migration.md —
  watch:js is Vite now` was edited. **That file is not in the tree** (the CSS
  migration notes live in `docs/ai/css.md`; the companion doc was only ever on
  the other branch) and the commit doesn't touch it.
- Plan doc header said "Status: plan only. Nothing here is committed work." —
  it *is* committed, in the same commit as the work it plans.

**Fix applied:**
- Plan doc: status → "executed", companion-doc link → `css.md`,
  `css-vite-migration.md` references → `css.md`.
- Progress doc: "Files changed" no longer claims an edit to a non-existent
  file; it now points at the plan/progress docs themselves.
- `docs/ai/css.md`: replaced the pre-existing dangling `css-vite-migration.md`
  link with a pointer to the JS migration progress doc.

**Notes:**
-

---

## 7. [Low] Minor nits

- [x] *(assessed)* `chunkName()` hardcodes
      `info.facadeModuleId.endsWith('/js/index.js')` for the `main` special case —
      a path-string hack; if `index.js` moves, `main.*.js` silently disappears.
      **Left as-is:** now extracted to `vite-js-plugins.mjs`, covered by a unit
      test (`names the app entry (index.js) "main"`), and the fallback chain
      makes the assumption explicit.
- [x] *(assessed)* `publicDir: '.'` cargo-culted from the CSS config — mostly
      inert for the JS build. **Left as-is:** it is load-bearing for the
      JS-imported stylesheet `url()` passthrough (same contract as the CSS
      build), and the parity harness + browser run confirm no `url()`
      regressions. Removing it is risk for zero gain.
- [x] *(assessed)* `legacy-datatables.css` change is CSS inside a JS-migration
      commit — justified (LightningCSS rejects IE star-hacks), and already
      documented in the progress doc's gotchas.

---

## Progress

- [x] #1 parity harness ref
- [x] #2 shared Vite config module
- [x] #3 derived Vite version
- [x] #4 dead webpackChunkName comments
- [x] #5 plugin tests (+ explicit imports as an optional follow-up)
- [x] #6 doc fixes
- [x] #7 minor nits (assessed, no change needed)

## Verification (all green)

- `scripts/js-build-parity.sh` → **PARITY OK** (webpack baseline + Vite rebuild,
  entries / chunk names / license headers / sourcemaps / sw.js shape / marker)
- jest: **35 suites, 583 tests pass** (incl. 16 new `vite-js-plugins` tests)
- eslint: clean on all changed files (only the expected self-ignore warning for
  `eslint.config.cjs`)
- All three `vite build` invocations (ESM + IIFE sw + IIFE partnerLib) succeed

_Last updated: 2026-08-13_
