# Front-End Dev Environment Guide

Lessons from building the `ol-search-bar` LIT component. These are the non-obvious
gotchas that will waste your day if you don't already know them.

---

## Build Commands: Which to Run and When

| What changed | Command |
|---|---|
| CSS / LESS only | `docker compose run --rm home make css` |
| JS only (`openlibrary/plugins/openlibrary/js/`) | `docker compose run --rm home make js` |
| Lit components (`openlibrary/components/lit/`) | `docker compose run --rm home make lit-components` |
| Templates only | `docker compose restart web` (no make needed) |
| Multiple or unsure | `docker compose run --rm home make all` |
| After any make | `docker compose restart web` to pick up new bundles |

**Do not skip `docker compose restart web`** after building JS or Lit components. The
web container caches the old bundle path and will serve stale assets.

After `make js` or `make lit-components`, always verify the build succeeded with zero
errors before restarting:

```bash
# Confirm the Lit bundle was written
ls -lh static/build/lit-components/ol-components.js
```

---

## LIT Component + jQuery Timing: The Load-Order Problem

**This is the single most dangerous trap when wiring a new Lit component into OL's jQuery code.**

`all.js` is loaded as a plain `<script>` tag (synchronous). `ol-components.js` (the Lit
bundle) is loaded as `<script type="module">` which is **always deferred** — it runs
after the page's HTML is parsed AND after all synchronous scripts. This means:

```
all.js runs  →  SearchBar constructor runs  →  jQuery finds nothing  →  ol-components.js finally runs  →  Lit renders
```

If you call `this.$component.find('input[type="text"]')` in a jQuery constructor, and
the Lit component hasn't rendered yet, you get an **empty set**. Event bindings on empty
sets silently do nothing. This looks like "clicking does nothing" — there is no error.

**The fix**: dispatch a custom event from the Lit component's `firstUpdated()` and defer
all DOM-dependent jQuery init until that event fires:

```js
// In the Lit component
firstUpdated() {
    this.dispatchEvent(new CustomEvent('ol-search-bar-ready'));
}

// In the jQuery class constructor
if (this._olSearchBar) {
    this._olSearchBar.addEventListener('ol-search-bar-ready', () => {
        this._initDomHandlers(urlParams);
    }, { once: true });
} else {
    this._initDomHandlers(urlParams);  // legacy path: no Lit, init immediately
}
```

`{ once: true }` is important — the event fires exactly once, and the listener removes
itself automatically.

**Any jQuery selector that touches Lit-rendered light DOM must be inside `_initDomHandlers`**, not in the constructor directly.

---

## Colima: LAN Access Doesn't Work Out of the Box

If you run Docker via Colima on a Mac and try to access `http://<your-LAN-IP>:8080`
from another device (phone, tablet, second laptop), it won't work even though
`lsof -i :8080` shows `*:8080 LISTEN`. Colima's Lima SSH tunnel binds the port to
`127.0.0.1` only.

**Workaround** — use `socat` to re-expose the port on all interfaces:

```bash
socat TCP-LISTEN:8081,bind=0.0.0.0,fork,reuseaddr TCP:127.0.0.1:8080
```

Then access via `http://<your-LAN-IP>:8081`. Run this in a background terminal or tmux
pane — it exits when you kill it.

---

## `/search.json` Always Returns 500 in Docker

**Symptom:** Autocomplete triggers a fetch to `/search.json?q=...` and gets a 500.
The search input appears to "do nothing" because the dropdown never populates.

**Root cause:** `openlibrary/core/lending.py:get_available_async` calls
`https://archive.org/services/availability/` on every search request. That URL is
unreachable from inside Docker containers in a local dev environment.

**This is a pre-existing dev environment limitation, not caused by your changes.** You
can verify it's not your bug:

```bash
# Check the web container logs for the real error
docker compose logs web --tail=30 | grep -i "availability\|ConnectionError\|aiohttp"
```

**Workaround:** Disable the lending API check in your local config. In
`openlibrary/conf/openlibrary.yml`, find `ia_availability_api_v2_url` and set it to an
empty string or a stub that returns `{}`. Then restart web.

This does NOT affect search results — it only suppresses the availability overlay on
search results (the "Borrow"/"Read" badges). Search still works for testing once this
is disabled.

---

## Playwright: File Extension Must Be `.mjs`

If `package.json` does not have `"type": "module"`, Playwright config and spec files
must use the `.mjs` extension:

```
playwright.config.mjs        ✓
tests/e2e/header-search.spec.mjs   ✓

playwright.config.js         ✗  (ReferenceError: require is not defined in ES module)
```

The `package.json` in this repo does NOT have `"type": "module"`, so use `.mjs`.

**Installing Playwright with a Node version mismatch:**

If `npm install @playwright/test` fails with `EBADENGINE` because your Node version
doesn't satisfy `"node":"^24.0.0"` in `package.json`, override the engine check:

```bash
npm_config_engine_strict=false npm install --save-dev @playwright/test
npx playwright install chromium
```

---

## pre-commit.ci Bot Commits Must Be Squashed

After you push a PR, pre-commit.ci may add a `[pre-commit.ci] auto fixes` commit (e.g.,
updating `messages.pot` when you remove or add `$_(...)` strings from templates).

These bot commits must be squashed into the parent commit before the PR is merged. To do
this interactively:

```bash
git fetch origin
git pull --rebase origin BRANCH      # pick up the bot commit
git log --oneline origin/master..HEAD  # confirm which commit to squash

# Squash: mark the bot commit as `squash` in the rebase editor
GIT_SEQUENCE_EDITOR='python3 -c "
import sys
lines = open(sys.argv[1]).readlines()
out = []
for line in lines:
    if \"pre-commit\" in line.lower():
        out.append(line.replace(\"pick\", \"squash\", 1))
    else:
        out.append(line)
open(sys.argv[1], \"w\").writelines(out)
"' git rebase -i origin/master

git push --force-with-lease origin BRANCH
```

Run `pre-commit run --files <changed files>` locally before pushing to minimize
how often the bot fires.

---

## Stylelint: Specificity Limit Workaround

Stylelint enforces a specificity limit (`selector-max-specificity`). The default cap is
`0,2,0` (two class selectors). If you need a three-class selector for state overrides
(e.g., `.header-bar .search-component.expanded ol-facet-select`), disable the rule
inline:

```css
/* stylelint-disable-next-line selector-max-specificity */
.header-bar .search-component.expanded ol-facet-select {
    display: inline-flex;
}
```

---

## Known Flaky Test: `test_olspy_sh.py::test_log_workers_cur_fn_fastapi`

This test fails when run as part of the full suite (`make test`) due to test ordering
— another test leaves state that breaks this one. It passes in isolation:

```bash
pytest tests/integration/test_olspy_sh.py::test_log_workers_cur_fn_fastapi -xvs
```

This is a **pre-existing flaky test on master**. If you see it fail in CI, check whether
it also fails on master's CI before investigating.

---

## CSS: Mirroring Existing Patterns for New Elements

When a new element (e.g. `ol-facet-select`) replaces an existing element (e.g.
`.search-facet`) in the DOM, check whether the existing element has any media-query or
state-driven visibility rules. You must mirror those rules for the new element.

Example: `.search-facet { display: none; }` at mobile widths (hidden until expanded)
needed to be matched with:

```css
.header-bar .search-component ol-facet-select {
    display: none;
}
/* stylelint-disable-next-line selector-max-specificity */
.header-bar .search-component.expanded ol-facet-select {
    display: inline-flex;
}
@media only screen and (min-width: 35.5em) {
    .header-bar .search-component ol-facet-select {
        display: inline-flex;
    }
}
```

Missing this causes the element to be visible in collapsed mobile state — a subtle but
visually obvious bug that only shows up at narrow viewport widths.

---

## Checking What's Actually Running

```bash
# What's listening on port 8080?
lsof -i :8080

# Which docker containers are running?
docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"

# Web container logs (look for errors after a restart)
docker compose logs web --tail=50 | grep -iE "error|exception|traceback"

# Check if bundles were built correctly
ls -lh static/build/lit-components/
ls -lh static/build/js/
```

---

## Quick Sanity Checks Before Reporting "It Works"

```bash
# HTTP 200 on homepage
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080
# Expected: 200

# JS tests
docker compose run --rm home npm run test:js

# Python tests
docker compose run --rm home make test

# Playwright E2E (desktop + mobile screenshots)
npx playwright test tests/e2e/header-search.spec.mjs
# Screenshots land in tests/e2e/screenshots/
```

Always view the Playwright screenshots — they catch mobile layout bugs (collapsed state,
hidden elements, wrong z-index) that HTTP 200 and passing unit tests do not catch.
