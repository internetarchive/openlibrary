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
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookiejar))

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
            raise SystemExit(f"{method} {path} failed: {e.code} {e.reason}\n{e.read().decode()[:500]}") from e


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
    web_client = Client(web_url, jar)  # web.py: login + reads + save_many
    fast_client = Client(fast_url, jar)  # FastAPI: the real merge endpoint

    print(f"==> Logging in as {username} on {web_url}")
    web_client.request("POST", "/account/login.json", {"username": username, "password": password})

    print(f"==> Creating authors {a_key}, {b_key}, {x_key} and edition {book_key} (listing A and B)")
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
    qs = urllib.parse.urlencode({"query": json.dumps({"key": book_key, "limit": 10})})
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
    print(f"Open it here (as a super-librarian, e.g. the dev 'openlibrary' user):\n\n    {final_url}\n")

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
        print("\nPASS: the undo was blocked and the page now shows:")
        start = page.find(EXPECTED_FLASH)
        snippet = page[start - 200 : start + 120].strip()
        print(f"    ...{snippet}...")
        print("\n(The exact wording lives in Changeset.get_undo_error() in openlibrary/plugins/upstream/models.py.)")
        return 0
    print("\nFAIL: the flash message was not found on the page after the undo POST.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
