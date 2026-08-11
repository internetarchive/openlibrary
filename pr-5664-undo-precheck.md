# PR: Explain why a merge can't be undone instead of returning a 500 (#5664, step 1)

---

## PR title (paste this into GitHub)

> **Explain why undoing an author merge fails instead of returning a 500 (#5664)**

---

## Description (paste this into the PR body)

### Summary

When a super-librarian clicks **Undo All** on an author merge, the request
currently ends in a 500 error page (`expected /type/author, found
/type/redirect`) whenever a pre-merge record references an author that has
*since* been merged into a different author by a **separate** merge
(internetarchive/openlibrary#5664).

The underlying save is atomic, so nothing is corrupted — the problem is
purely that the failure is silent and opaque to the librarian.

This PR is deliberately a **first step**: it does not change undo semantics.
It makes the failure *visible and explainable* so the issue can be properly
triaged and eventually fixed:

1. **Pre-check** (`Changeset.get_undo_error()`): before attempting an undo,
   the changeset's pre-merge (`revision − 1`) documents are scanned for the
   exact condition infobase's `SaveProcessor` will reject — a reference to a
   record that no longer exists, or whose current type is `/type/redirect`
   (i.e. it was merged into another record by a different changeset).
2. **Flash message**: if the pre-check finds a problem, the undo is *not
   attempted* and the page shows a specific, accurate error banner instead,
   e.g.:

   > This merge cannot be undone automatically because `/books/OL…M`
   > references `/authors/OL…A`, which has since been merged into another
   > record.

3. **Fallback catch**: any other `ClientException` during the undo save is
   logged server-side with a full traceback, and a generic flash message is
   shown — so even failures the pre-check can't anticipate never surface as
   a bare 500.

### What this PR deliberately does NOT do

- It does **not** make the undo succeed. Records that can't be undone still
  can't be undone.
- It does **not** loosen infobase's type validation (that would be a bad
  trade for every Infogami site).
- The real fix (restoring referenced redirect authors in the undo batch, or
  following redirects) is a separate follow-up; the design space is mapped
  in `issue-5664-merge-undo.md`.

### Files changed

| File | Change |
|---|---|
| `openlibrary/plugins/upstream/models.py` | New `find_references()` helper + `Changeset.get_undo_error()` pre-check |
| `openlibrary/plugins/upstream/recentchanges.py` | `recentchanges_view.POST` runs the pre-check, flashes the message, and catches `ClientException` as a fallback; added a `404` guard for unknown changesets |
| `openlibrary/tests/plugins/upstream/test_recentchanges_undo.py` | 7 tests: pre-check reports redirect refs / missing refs, passes when refs are valid; handler flashes / undoes / requires super-librarian / falls back on unexpected failures |
| `scripts/reproduce_issue_5664.py` | Self-contained reproducer that builds the #5664 scenario in a local dev DB and can trigger the undo (see below) |

---

## How to reproduce (exact steps, verified)

The script below creates the **exact #5664 shape** in your local dev database
using only real code paths (the real merge endpoint, real changesets, real
undo POST):

> A book lists authors **A** and **B**. Merge **A → X**, then merge **B → X**.
> Now undoing the *first* merge would restore the book to a revision that
> lists **B** — but **B** is a `/type/redirect` today (merged by the second
> merge) and is **not** part of the first merge's changeset. That is
> precisely the condition that makes infobase reject the undo save.

### 1. Prerequisites

- Dev environment running: `make git && docker compose up` (web.py on
  `http://localhost:8080`, FastAPI on `http://localhost:18080`).
- The seeded dev user (`openlibrary` / `openlibrary`), which is a member of
  `/usergroup/admin` and therefore a super-librarian.
- Python 3 (any version) on the host — the script uses only the stdlib.

### 2. Run it

```bash
cd /path/to/openlibrary

# Option A: set up the scenario, print the URL, and stop (you click the button)
python3 scripts/reproduce_issue_5664.py

# Option B: set up the scenario AND trigger the undo, asserting the flash message
python3 scripts/reproduce_issue_5664.py --test-undo
```

### 3. What you should see

With `--test-undo` (this PR's code running):

```
==> Logging in as openlibrary on http://localhost:8080
==> Creating authors /authors/repro_a_1786477949, ... and edition /books/repro_1786477949 (listing A and B)
==> Merge #1: A into X (the changeset we will undo)
==> Merge #2: B into X (makes B a redirect outside merge #1's changeset)

Merge #1 changeset id: 82
Open it here (as a super-librarian, e.g. the dev 'openlibrary' user):

    http://localhost:8080/recentchanges/2026/08/11/merge-authors/82

==> POSTing the undo (this is what the 'Undo All' button does)

PASS: the undo was blocked and the page now shows:
    ...<div class="flash-messages">
    <div class="error"><span>This merge cannot be undone automatically because
    /books/repro_1786477949 references /authors/repro_b_1786477949, which has since b...
```

Without this PR (or with `--test-undo` against old code), the same POST
returns **HTTP 500** with `expected /type/author, found /type/redirect`.

### 4. Manual / browser verification

1. Open the URL printed by the script (or, if you have the real data copied
   into your dev DB, e.g. `/recentchanges/2014/04/04/merge-authors/47986246`).
2. Click **Undo All**.
3. You are redirected back to the same page, and a red error banner explains
   exactly why the undo can't run — naming the record and the reference.

### Script source (`scripts/reproduce_issue_5664.py`)

```python
#!/usr/bin/env python3
"""Reproduce internetarchive/openlibrary#5664 in the local dev environment.

Undoing an author merge returns a 500 ("expected /type/author, found
/type/redirect") when a pre-merge edition references an author that has
since been merged into a *different* author by a separate merge. This
script creates exactly that shape in the local dev database:

  1. Creates three authors (A, B, X) and one edition listing A and B.
  2. Merges A into X via the real merge endpoint (merge #1 - the
     changeset we will try to undo).
  3. Merges B into X via the real merge endpoint (merge #2 - makes B a
     /type/redirect *outside* merge #1's changeset, the exact #5664
     condition).
  4. Prints the recentchanges URL for merge #1.
  5. With --test-undo, POSTs the undo and reports whether the new
     pre-check flashes a clear message (new code) or the undo 500s
     (old code).

Requirements: a running dev environment (`make git && docker compose up`),
plus the seeded dev user (openlibrary / openlibrary, a super-librarian).

Usage:
    python3 scripts/reproduce_issue_5664.py
    python3 scripts/reproduce_issue_5664.py --test-undo
    OL_URL=http://localhost:8080 OL_FAST_URL=http://localhost:18080 \\
        python3 scripts/reproduce_issue_5664.py
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

EXPECTED_FLASH = "cannot be undone automatically"


class Client:
    """Tiny HTTP client with session-cookie support (stdlib only)."""

    def __init__(self, base_url: str, cookiejar: CookieJar):
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookiejar)
        )

    def request(self, method, path, body=None, headers=None):
        url = self.base_url + path
        data = None
        headers = dict(headers or {})
        if body is not None:
            data = json.dumps(body).encode()
            headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            resp = self.opener.open(req)
            return resp.geturl(), resp.read().decode()
        except urllib.error.HTTPError as e:
            raise SystemExit(
                f"{method} {path} failed: {e.code} {e.reason}\n{e.read().decode()[:500]}"
            ) from e


def main():
    parser = argparse.ArgumentParser(description="Reproduce #5664 in the local dev DB.")
    parser.add_argument(
        "--test-undo",
        action="store_true",
        help="Also POST the undo and verify the result (new code flashes a message).",
    )
    args = parser.parse_args()

    web_url = os.environ.get("OL_URL", "http://localhost:8080")
    fast_url = os.environ.get("OL_FAST_URL", "http://localhost:18080")
    username = os.environ.get("OL_USERNAME", "openlibrary")
    password = os.environ.get("OL_PASSWORD", "openlibrary")

    # Unique keys so the script can be re-run without collisions.
    suffix = str(int(time.time()))
    a_key, b_key, x_key = (
        f"/authors/repro_a_{suffix}",
        f"/authors/repro_b_{suffix}",
        f"/authors/repro_x_{suffix}",
    )
    book_key = f"/books/repro_{suffix}"

    jar = CookieJar()
    web_client = Client(web_url, jar)   # web.py: login + reads + save_many
    fast_client = Client(fast_url, jar)  # FastAPI: the real merge endpoint

    print(f"==> Logging in as {username} on {web_url}")
    web_client.request(
        "POST", "/account/login.json", {"username": username, "password": password}
    )

    print(
        f"==> Creating authors {a_key}, {b_key}, {x_key} and edition "
        f"{book_key} (listing A and B)"
    )
    web_client.request(
        "POST",
        "/api/save_many",
        [
            {"key": a_key, "type": {"key": "/type/author"}, "name": "Repro Alpha"},
            {"key": b_key, "type": {"key": "/type/author"}, "name": "Repro Beta"},
            {"key": x_key, "type": {"key": "/type/author"}, "name": "Repro X"},
            {
                "key": book_key,
                "type": {"key": "/type/edition"},
                "title": f"Repro book {suffix}",
                "authors": [{"key": a_key}, {"key": b_key}],
            },
        ],
    )

    print("==> Merge #1: A into X (the changeset we will undo)")
    fast_client.request(
        "POST",
        "/authors/merge.json",
        {"master": x_key, "duplicates": [a_key], "comment": "repro #5664 merge #1"},
    )

    print("==> Merge #2: B into X (makes B a redirect outside merge #1's changeset)")
    fast_client.request(
        "POST",
        "/authors/merge.json",
        {"master": x_key, "duplicates": [b_key], "comment": "repro #5664 merge #2"},
    )

    # Find merge #1's changeset: scan the book's version history (newest
    # first) for the version whose changeset contains A's redirect.
    cid = None
    qs = urllib.parse.urlencode(
        {"query": json.dumps({"key": book_key, "limit": 10})}
    )
    _, body = web_client.request("GET", "/api/versions?" + qs)
    versions = json.loads(body).get("result", [])
    for version in versions:
        changes = version.get("changes") or []
        if isinstance(changes, str):
            changes = json.loads(changes)
        if a_key in {c["key"] for c in changes}:
            cid = version["id"]
            break
    if cid is None:
        raise SystemExit("Could not find merge #1's changeset in the book's version history.")

    final_url, _ = web_client.request("GET", f"/recentchanges/goto/{cid}")
    print(f"\nMerge #1 changeset id: {cid}")
    print(
        f"Open it here (as a super-librarian, e.g. the dev 'openlibrary' user):"
        f"\n\n    {final_url}\n"
    )

    if not args.test_undo:
        print(
            "Click the 'Undo All' button on that page.\n"
            "  * With this PR: a red banner explains why the undo can't run.\n"
            "  * Without it: the page 500s with 'expected /type/author, found /type/redirect'.\n"
            "\nRe-run with --test-undo to trigger the undo from this script instead."
        )
        return 0

    print("==> POSTing the undo (this is what the 'Undo All' button does)")
    path = urllib.parse.urlparse(final_url).path
    # urllib follows the 303 redirect to the change page, which is where the
    # flash message is rendered (it lives in a cookie, consumed on first load).
    _, page = web_client.request("POST", path)
    if EXPECTED_FLASH in page:
        print(f"\nPASS: the undo was blocked and the page now shows:")
        start = page.find(EXPECTED_FLASH)
        snippet = page[start - 200 : start + 120].strip()
        print(f"    ...{snippet}...")
        print(
            "\n(The exact wording lives in Changeset.get_undo_error() in "
            "openlibrary/plugins/upstream/models.py.)"
        )
        return 0
    print("\nFAIL: the flash message was not found on the page after the undo POST.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

---

## Validation

- `openlibrary/tests/plugins/upstream/test_recentchanges_undo.py`: **7/7 pass**;
  broader smoke (`openlibrary/tests/plugins/upstream/` +
  `openlibrary/tests/core/test_processors.py` + `test_connections.py`): **18 pass**.
- `ruff check` and `ruff format --check` clean on all changed files.
- End-to-end: the reproduction script above was run against the local dev
  instance — the undo POST is blocked and the flash message renders.

---

## Next steps (not in this PR)

The pre-check makes the failure diagnosable; the fix itself is mapped out in
`issue-5664-merge-undo.md`:

- **Approach A — restore referenced redirect authors**: pull the pre-merge
  revisions of referenced-but-now-redirect authors into the undo batch so
  they're revived as authors (faithful "time machine" undo; re-creates
  duplicates that later merges resolved).
- **Approach B — follow redirects**: rewrite the restored documents to point
  at the redirect targets (preserves later merge decisions; the book ends up
  crediting authors it never listed).
- **Approach C — hybrid**: per-reference decision, e.g. restore authors whose
  redirect postdates the merge being undone.

`MergeWorks` undo has the same shape and would benefit from the same
treatment.
