# End-to-end tests

Playwright specs that drive a real browser against a running Open Library.

## Running them

```bash
make e2e-up      # stack, assets, Solr index, browser — once per session
make test-e2e    # the suite
```

`make e2e-up` starts the Docker services, rebuilds `static/build` from your
working tree, indexes the seed data into Solr if the index is empty, and
installs Chromium. Re-running it is cheap: each step skips when it can.

Narrow a run with `PLAYWRIGHT_ARGS`, which is passed straight to Playwright:

```bash
make test-e2e PLAYWRIGHT_ARGS="search --headed"
```

Tests hit `http://localhost:8080` by default. Point them elsewhere with `OL_BASE_URL`.

Two projects are configured so nothing runs twice: `desktop` runs everything
except `@mobile`, and `mobile` runs only `@mobile`.

### Why the asset rebuild matters

`static/build` is a named volume seeded from the `oldev` image, which is built
on `openlibrary/olbase` — rebuilt weekly, with `make` run at image build time
against **master**. Skip the rebuild and the browser loads last week's bundles,
so a spec covering your own JS or Lit component passes without ever running
your code. `make e2e-assets` is that rebuild; `make e2e-up` includes it.

### Where these run

Nowhere automatic, yet. There is no CI job and no pre-commit hook — run them
locally when you touch templates, JS, or a Lit component. `visual.spec.ts` is
opt-in behind `OL_VISUAL=1` and stays out of CI permanently: full-page
screenshots differ with platform font rendering.

## Logged-in tests

Most specs check pages anonymously, then again inside a
`test.describe('when logged in')` block. `login(page)` in `helpers.ts` posts to
`/account/login.json`, which drops the session cookie into the browser
context, so the next `page.goto()` is already authenticated:

```javascript
import { collectConsoleErrors, login } from './helpers';

test.describe('when logged in', () => {
    test.beforeEach(({ page }) => login(page));

    test('loads', async ({ page }) => { /* ... */ });
});
```

Against the local stack it uses the seeded `openlibrary` / `openlibrary`
patron. Against any other host set credentials, or logged-in tests skip:

| Variable | Used for |
|---|---|
| `OL_E2E_USERNAME` / `OL_E2E_PASSWORD` | `login()` session helper (infogami username + password) |
| `OL_E2E_S3_ACCESS` / `OL_E2E_S3_SECRET` | `login()` with IA S3 keys instead |
| `OL_E2E_EMAIL` | tests that drive the login form, which authenticates against IA by email |

The dev mock IA auth (`docker/mockservices/main.py`) accepts any email with any
non-empty password, so it can't tell a wrong password from a right one — except
the sentinel `bad_password`, which it rejects. Use that when a test needs the
login-failure path.

### Watching them run

```bash
npx playwright test --ui        # interactive runner
npx playwright test --headed    # visible browser, driven live
```

These are not the same thing. `--ui` runs headless and records a trace you
scrub through afterwards: pick a test, click an action, and the pane shows the
real DOM at that moment. It does not open a browser window, and the pane stays
blank until you select an individual test rather than its `describe` block.
`--headed` is the one that opens Chromium and lets you watch it work. Add
`--slow-mo=1000` to follow along.

After any run, `npx playwright show-report` opens the HTML report.

## Accessibility tests

`a11y.ts` wraps [`@axe-core/playwright`](https://github.com/dequelabs/axe-core-npm)
with Open Library's conformance target, WCAG 2.1 AA.

These complement the component tests in `openlibrary/components/__tests__/`
rather than duplicating them. Those run in jsdom, which parses markup but never
lays it out, so they can check ARIA wiring and nothing else. **Colour contrast,
focus styling, and anything else that needs rendered pixels can only be tested
here.**

### Scanning a page

```javascript
import { a11yCheck, expectNoViolations, THIRD_PARTY_FRAMES } from './a11y';

test('my page is accessible', async ({ page }) => {
    await page.goto('/my-page');
    expectNoViolations(await a11yCheck(page, { exclude: THIRD_PARTY_FRAMES }));
});
```

`expectNoViolations` prints every violation with its impact, the offending
markup, and remediation steps, rather than Playwright's default array diff.

### The pattern for a11y fix PRs

A fix PR should ship a test that proves the fix and fails without it. Scope it
to the rule you fixed, so it stays green while unrelated violations elsewhere on
the page are still outstanding:

```javascript
test('iframes have accessible titles', async ({ page }) => {
    await page.goto('/');
    expectNoViolations(await a11yCheck(page, { rules: ['frame-title'] }));
});
```

Before you commit, **check the test fails without your fix.** A scoped rule that
matches no elements passes trivially, which looks identical to a fix that works.

### Options

| Option | Effect |
|---|---|
| `rules` | Run only these rule ids. Skips the WCAG tag filter entirely. |
| `include` | CSS selector to scan. Defaults to the whole page. |
| `exclude` | CSS selectors to skip, e.g. `THIRD_PARTY_FRAMES`. |
| `disableRules` | Rule ids to skip. Prefer `rules` for fix-PR tests. |

### Third-party content

The a11y specs block `archive.org` requests before navigating, so the donation
banner never loads. Axe *does* see inside cross-origin iframes under Playwright
(injection happens over the devtools protocol, not from the page), and the
banner's content rotates by campaign — some variants fail `image-alt` — so an
unblocked scan could flip between runs with no Open Library change.

`THIRD_PARTY_FRAMES` additionally excludes any iframe from the scan, for
embeds that aren't ours to fix. Pass it explicitly rather than relying on a
default, so any test that skips part of the page says so in its own body.
