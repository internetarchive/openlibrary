#!/usr/bin/env python
"""
Comments on a pull request that edits `openlibrary/i18n/<lang>/messages.po`
for a language that internetarchive/openlibrary-i18n also has.

Translations are maintained in openlibrary-i18n. Once `docker/Dockerfile.olbase`
copies its `.po` files over ours (#13070), an edit here for one of those
languages is overwritten at image build and never reaches production.

Keeps a single comment per PR, found by a marker: it is created when the PR
first edits an affected file, updated on later pushes, and marked resolved if
the edits are removed.

Run from a checkout of the PR's *base* branch; `docker/Dockerfile.olbase` is
read from that checkout to decide whether the overwrite is already in place.

Environment: GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER.
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

API = "https://api.github.com"
I18N_REPO = "internetarchive/openlibrary-i18n"
MARKER = "<!-- po-edit-warning -->"
BOT_LOGIN = "github-actions[bot]"
PO_PATH = re.compile(r"^openlibrary/i18n/([^/]+)/messages\.po$")
DOCKERFILE = Path("docker/Dockerfile.olbase")


def affected_languages(changed_files: list[str], i18n_languages: set[str]) -> list[str]:
    """Languages whose `messages.po` the PR edits and openlibrary-i18n also has."""
    edited = {m.group(1) for f in changed_files if (m := PO_PATH.match(f))}
    return sorted(edited & i18n_languages)


# Either form #13070 has taken: an inline clone, or the pull script it now runs.
OVERWRITE_SIGNS = (f"github.com/{I18N_REPO}", "i18n-pull-translations")


def overwrite_in_place(dockerfile_text: str) -> bool:
    """Whether the olbase image build already pulls openlibrary-i18n's `.po` files."""
    code = "\n".join(line for line in dockerfile_text.splitlines() if not line.lstrip().startswith("#"))
    return any(sign in code for sign in OVERWRITE_SIGNS)


def render_comment(languages: list[str], in_place: bool) -> str:
    if not languages:
        return f"{MARKER}\nThis PR no longer edits any `messages.po` file that openlibrary-i18n also has. Resolved."

    files = "\n".join(f"- `openlibrary/i18n/{lang}/messages.po`" for lang in languages)
    when = (
        "The production image copies openlibrary-i18n's `.po` files over these at build time"
        if in_place
        else "Once #13070 lands, the production image will copy openlibrary-i18n's `.po` files over these at build time"
    )
    delay = "" if in_place else " A change made there reaches openlibrary.org when #13070 ships, not before; that delay is expected, and the change is not lost."
    return (
        f"{MARKER}\n"
        "**Translations for these languages are maintained in "
        f"[{I18N_REPO}](https://github.com/{I18N_REPO}), not here.**\n\n"
        f"This PR edits:\n{files}\n\n"
        f"{when}, so a change merged here is overwritten and never reaches openlibrary.org. "
        "(The one exception: a language whose openlibrary-i18n file fails the build's safety check keeps this repository's file for that build.) "
        "Nothing reports an error when that happens.\n\n"
        f"Please make the same change to `locale/<lang>/messages.po` in [{I18N_REPO}](https://github.com/{I18N_REPO}) instead."
        f"{delay} New or changed English strings, and the regenerated `openlibrary/i18n/messages.pot`, still belong in this repository.\n\n"
        "_Posted by `.github/workflows/po_edit_warning.yml`._"
    )


def _request(method: str, url: str, token: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        link = resp.headers.get("Link", "")
        return json.load(resp), link


def _get_all(url: str, token: str) -> list:
    items: list = []
    while url:
        page, link = _request("GET", url, token)
        items.extend(page)
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else ""
    return items


def main() -> int:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    pr = int(os.environ["PR_NUMBER"])

    changed = [f["filename"] for f in _get_all(f"{API}/repos/{repo}/pulls/{pr}/files?per_page=100", token)]
    locale, _ = _request("GET", f"{API}/repos/{I18N_REPO}/contents/locale?ref=main", token)
    i18n_languages = {entry["name"] for entry in locale if entry["type"] == "dir"}
    languages = affected_languages(changed, i18n_languages)

    comments = _get_all(f"{API}/repos/{repo}/issues/{pr}/comments?per_page=100", token)
    existing = next((c for c in comments if c["user"]["login"] == BOT_LOGIN and c["body"].startswith(MARKER)), None)

    if not languages and existing is None:
        print("No affected messages.po edits; nothing to do.")
        return 0

    body = render_comment(languages, overwrite_in_place(DOCKERFILE.read_text()))
    if existing is None:
        _request("POST", f"{API}/repos/{repo}/issues/{pr}/comments", token, {"body": body})
        print(f"Commented: {languages}")
    elif existing["body"] != body:
        _request("PATCH", existing["url"], token, {"body": body})
        print(f"Updated comment: {languages}")
    else:
        print("Comment already current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
