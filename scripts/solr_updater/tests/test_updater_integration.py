"""Run the real poll loop against a real Solr and the real mock index.

Replaces an 878-line standalone harness that reimplemented the updater's logic
so a reviewer could watch it, plus a 92-line guard whose only job was keeping
that copy in sync with the original. The copy drifted anyway, and a guard
against drift between a thing and its copy is a copy-shaped problem.

This exercises `main()` itself. The worst defect this change ever had was a
cold start that could never complete against production's `maxBooleanClauses`,
and it survived 8/8 green CI because nothing had executed the daemon anywhere.

What v3 makes testable that v2 could not: the mock's unavailable set is
controllable and can CHANGE between polls, so "a book was returned", "a book
was borrowed" and "the field was wiped by a reindex" are all stageable rather
than raced for. The previous version of this file asserted on whatever the
live feed happened to do during a 30-second window and was flaky twice over.

NOT covered here, deliberately: the clear-direction breaker and its
ground-truth confirmation. Tripping it needs more marked editions than the
floor and then depends on what the mock's availability matrix says about each
one, which would make the assertion fuzzy -- the unit tests pin that behaviour
exactly, per edition, and this would only add a vaguer second opinion.

Skipped unless both services are reachable, so it is a no-op in CI and a real
check locally. To run it:

    docker compose up -d --no-build mockservices solr
    docker compose run --rm --no-deps \\
      -e SOLR_URL=http://solr:8983/solr/openlibrary \\
      -e MOCKSERVICES_URL=http://mockservices:8090 \\
      home python -m pytest scripts/solr_updater/tests/test_updater_integration.py

If Solr will not start because host port 8983 is taken by another project, do
not treat that as a blocker and do not go looking for whoever took it. Nothing
here needs the host port -- these tests run inside the compose network, where
8983 is per-container. Drop the publish and start it again:

    printf 'services:\\n  solr:\\n    ports: !reset []\\n' > .solr-noport.yaml
    docker compose -f compose.yaml -f .solr-noport.yaml up -d --no-build solr

And if the `solr` HOSTNAME resolves to a container from somewhere else -- any
container attached to this project's network can hold that alias -- address
your own by its IP instead of hunting for the name:

    docker inspect <project>-solr-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'

Both of these cost one line. Confirm which Solr you actually reached before
believing a green run: a document count in your own core is the control, and
an earlier revision of this file reported three passes against a different
project's Solr entirely.
"""

import asyncio
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import AsyncMock, patch

import pytest

from scripts.solr_updater.loan_availability_updater import main

SOLR = os.environ.get("SOLR_URL", "http://localhost:8984/solr/openlibrary")
FEED = os.environ.get("MOCKSERVICES_URL", "http://localhost:8090")

WORK_PREFIX, EDITION_PREFIX = "/works/OL7700", "/books/OL7700"
OCAIDS = [f"integration{i:03d}" for i in range(6)]


def _reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=3).read()
        return True
    except urllib.error.URLError, OSError:
        return False


pytestmark = pytest.mark.skipif(
    not (_reachable(f"{SOLR}/admin/ping") and _reachable(f"{FEED}/health")),
    reason="needs a Solr and a mockservices index; see this module's docstring",
)


def _post(path: str, payload) -> dict:
    req = urllib.request.Request(f"{SOLR}/{path}", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def _commit() -> None:
    urllib.request.urlopen(f"{SOLR}/update?commit=true", timeout=30).read()


def _edition(key: str) -> dict:
    return json.load(urllib.request.urlopen(f"{SOLR}/get?id={urllib.parse.quote(key)}&wt=json", timeout=10)).get("doc") or {}


def _set_index(identifiers: list[str]) -> None:
    """Replace what the mock index calls checked out."""
    req = urllib.request.Request(
        f"{FEED}/_test/unavailable",
        data=json.dumps({"identifiers": identifiers}).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    urllib.request.urlopen(req, timeout=10).read()


@pytest.fixture
def seeded_editions():
    """Six editions, one per ocaid, with no availability field of their own.

    Posted as full documents, which is also how a reindex writes them -- so
    re-running this fixture is exactly the wipe the self-heal test needs.
    """

    def write() -> list[str]:
        _post(
            "update",
            [
                {
                    "key": f"{WORK_PREFIX}{i}W",
                    "type": "work",
                    "title": f"Integration {i}",
                    "editions": [{"key": f"{EDITION_PREFIX}{i}M", "type": "edition", "work_key": [f"{WORK_PREFIX}{i}W"], "ia": [ocaid]}],
                }
                for i, ocaid in enumerate(OCAIDS)
            ],
        )
        _commit()
        return [f"{EDITION_PREFIX}{i}M" for i in range(len(OCAIDS))]

    return write


async def _one_poll() -> None:
    """Run main()'s real loop for exactly one cycle.

    Stopped by making the sleep at the end of a cycle raise, rather than by
    bounding the wall clock: a timeout can stop the loop mid-write and makes
    the assertion depend on how fast the machine is.
    """
    with (
        patch("scripts.solr_updater.loan_availability_updater.asyncio.sleep", AsyncMock(side_effect=SystemExit)),
        pytest.raises(SystemExit),
    ):
        await main("conf/openlibrary.yml", poll_interval=0)


def test_a_poll_marks_what_the_index_calls_unavailable(seeded_editions, monkeypatch):
    monkeypatch.setenv("OL_SOLR_BASE_URL", SOLR)
    keys = seeded_editions()
    _set_index(OCAIDS[:3])

    asyncio.run(_one_poll())
    _commit()

    marked = {key for key in keys if _edition(key).get("ebook_unavailable") == 1}
    assert marked == set(keys[:3]), "exactly the editions the index calls unavailable must be marked"

    # The only COMMITTED check that `ebook_unavailable_ts` survives a real
    # round trip. The unit tests mock Solr out, so nothing else would catch a
    # schema/code field-name mismatch, a type the schema rejects, or the field
    # silently not being declared -- and that last one is the deploy failure
    # this field newly makes possible. Bounded against the clock for the same
    # reason the unit test is: milliseconds and a frozen value both read as
    # "a number" otherwise.
    now = int(time.time())
    for key in marked:
        ts = _edition(key).get("ebook_unavailable_ts")
        assert ts is not None, f"{key} is marked but carries no ebook_unavailable_ts; is the field declared in the schema?"
        assert now - 300 <= ts <= now + 60, f"{key} ts={ts} is not epoch seconds near now ({now})"


def test_a_poll_clears_a_book_the_index_has_released(seeded_editions, monkeypatch):
    """The direction the repairer used to own, now in the same operation."""
    monkeypatch.setenv("OL_SOLR_BASE_URL", SOLR)
    keys = seeded_editions()
    _set_index(OCAIDS[:3])
    asyncio.run(_one_poll())
    _commit()

    _set_index(OCAIDS[:1])
    asyncio.run(_one_poll())
    _commit()

    assert _edition(keys[0]).get("ebook_unavailable") == 1, "still out"
    assert _edition(keys[1]).get("ebook_unavailable") == 0, "returned, so freed"
    # requireInPlace cannot null a field, so a clear leaves the stamp behind.
    # Verified here rather than only in a unit test, because the claim is about
    # what SOLR does, not about what the daemon sends.
    assert _edition(keys[1]).get("ebook_unavailable_ts") is not None, "a clear must leave the old stamp in place, not remove it"
    assert _edition(keys[2]).get("ebook_unavailable") == 0, "returned, so freed"


def test_a_reindex_wipe_is_repaired_by_the_next_poll(seeded_editions, monkeypatch):
    """HEADLINE. A reindex rewrites edition documents and drops
    `ebook_unavailable` entirely. Under the design this replaces, every
    checked-out book was then published as borrowable until somebody re-ran a
    cold start by hand -- an operator step that could be forgotten, and whose
    omission looked exactly like a healthy index. Here the next poll simply
    sees an empty marked set and marks the whole unavailable set again.
    """
    monkeypatch.setenv("OL_SOLR_BASE_URL", SOLR)
    keys = seeded_editions()
    _set_index(OCAIDS[:3])
    asyncio.run(_one_poll())
    _commit()
    assert _edition(keys[0]).get("ebook_unavailable") == 1, "precondition: the first poll marked it"

    # The wipe: re-post the documents in full, exactly as a reindex does.
    seeded_editions()
    assert _edition(keys[0]).get("ebook_unavailable") is None, "precondition: the field is gone, not zeroed"

    asyncio.run(_one_poll())
    _commit()

    healed = {key for key in keys if _edition(key).get("ebook_unavailable") == 1}
    assert healed == set(keys[:3]), "the next poll must restore every mark with no operator step"
