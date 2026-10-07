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
import datetime
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infogami import config
from openlibrary.config import load_config
from openlibrary.core import lending
from openlibrary.utils.request_context import create_context_for_script, req_context
from scripts.solr_updater.loan_availability_updater import _poll_loop, confirm_clears, follow_feed_once

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


def _ensure_config() -> None:
    """main() loads the config and wires lending; the loop functions do not.

    Driving a loop directly skips that, and the symptom is remote: the daemon
    falls back to a bookreader host that is unset, so the URL has the literal
    string "None" for a hostname and the failure surfaces as a DNS error from
    inside an exception handler that swallows it. Doing it here keeps the tests
    on the shipping loop functions without pretending main() does nothing.
    """

    if not config.get("plugin_openlibrary"):
        load_config("conf/openlibrary.yml")
        lending.setup(config)
    req_context.set(create_context_for_script())


async def _one_poll() -> None:
    """Run the REAL poll loop for exactly one cycle.

    Not main(): in the hybrid that runs the feed loop alongside this one under
    asyncio.gather and bootstraps a cursor first, so it is the wrong entry
    point for a test about the poll. _poll_loop is the shipping function these
    tests were always about.

    Stopped by making the sleep at the end of a cycle raise, rather than by
    bounding the wall clock: a timeout can stop the loop mid-write and makes
    the assertion depend on how fast the machine is.
    """
    _ensure_config()
    with (
        patch("scripts.solr_updater.loan_availability_updater.asyncio.sleep", AsyncMock(side_effect=SystemExit)),
        pytest.raises(SystemExit),
    ):
        await _poll_loop(poll_interval=0, es_lag_margin=0, dry_run=False)


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
    # silently not being declared -- and on THIS branch that last one is not
    # merely a lost diagnostic: the gate reads the stamp, so an undeclared
    # field turns every mark into an unstamped one and the whole clear-side
    # protection degrades without a word. Bounded against the clock for the
    # same reason the unit test is: milliseconds and a frozen value both read
    # as "a number" otherwise.
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
    assert _edition(keys[2]).get("ebook_unavailable") == 0, "returned, so freed"

    # requireInPlace cannot null a field, so a clear leaves the stamp behind.
    # Verified here rather than only in a unit test, because the claim is about
    # what SOLR does, not about what the daemon sends.
    assert _edition(keys[1]).get("ebook_unavailable_ts") is not None, "a clear must leave the old stamp in place, not remove it"


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


# ---------------------------------------------------------------------------
# The hybrid's reason for existing, end to end on the shipping daemon: the feed
# and the index DISAGREE, with the feed ahead, and the timestamp gate decides
# who wins. Everything above tests the poll alone.
# ---------------------------------------------------------------------------

FRESH_OCAID = "hybridfresh001"
FRESH_WORK, FRESH_EDITION = "/works/OL7790W", "/books/OL7790M"


def _reset_feed() -> None:
    """Unfreeze and re-seed the mock's feed.

    Staging a window freezes the dev generator so the staged rows hold still.
    That is necessary and it leaves the container in a state the next test does
    not expect -- one hand-written row where a realistic feed should be. Two
    container-gated tests next door broke on exactly that before this existed.
    """
    req = urllib.request.Request(f"{FEED}/_test/loan_changes/reset", data=b"", method="POST")
    urllib.request.urlopen(req, timeout=30).read()


def _set_feed(rows: list[dict]) -> None:
    req = urllib.request.Request(
        f"{FEED}/_test/loan_changes",
        data=json.dumps({"rows": rows}).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    urllib.request.urlopen(req, timeout=10).read()


def _seed_one_edition() -> None:
    _post(
        "update",
        [
            {
                "key": FRESH_WORK,
                "type": "work",
                "title": "Hybrid disagreement",
                "editions": [{"key": FRESH_EDITION, "type": "edition", "work_key": [FRESH_WORK], "ia": [FRESH_OCAID]}],
            }
        ],
    )
    _commit()


async def _feed_once(cursor: int = 1) -> int:
    _ensure_config()
    return await follow_feed_once(cursor, dry_run=False)


async def _poll_once(margin: int) -> MagicMock:
    """One cycle of the REAL poll loop, stopped by its own sleep.

    Returns a spy wrapping `confirm_clears`, so a caller can tell WHICH layer
    held a clear: never called means the timestamp gate removed it before the
    confirmation stage, called means the gate let it through and ground truth
    decided. `wraps` keeps the real implementation, so this observes without
    changing what runs.
    """
    _ensure_config()
    spy = MagicMock(wraps=confirm_clears)
    with (
        patch("scripts.solr_updater.loan_availability_updater.confirm_clears", spy),
        patch("scripts.solr_updater.loan_availability_updater.asyncio.sleep", AsyncMock(side_effect=SystemExit)),
        pytest.raises(SystemExit),
    ):
        await _poll_loop(poll_interval=0, es_lag_margin=margin, dry_run=False)
    return spy


def test_a_fresh_feed_mark_survives_a_poll_that_would_otherwise_clear_it(monkeypatch):
    """THE HYBRID, on the real daemon, against real Solr and both mocks.

    The feed sees a borrow. The index has not caught up, so the book is ABSENT
    from its unavailable set — which, to a poll-only daemon, is indistinguishable
    from "returned". Under #12689 that book is cleared and published as
    borrowable while someone has it; the whole point of this design is that it
    is not.

    Staged rather than raced: the index is set to say nothing is checked out
    and the feed is set to a borrow timestamped now, so the disagreement is
    deterministic. Then the SAME daemon code is run with two margins — a day,
    under which the mark is too fresh to contradict, and one second, under
    which it is not.

    **The book stays marked under BOTH margins, and the margins are what make
    them different cases.** Under the day margin the timestamp gate holds it
    and ground truth is never consulted. Under the one-second margin the gate
    lets it through and ground truth holds it instead — correctly, because the
    book genuinely IS on loan: a borrow five seconds old is checked out, and
    the index is simply late. So this asserts WHICH LAYER held it each time,
    from the daemon's own logs, rather than asserting an outcome both layers
    produce.

    That the tight-margin half can no longer show a clear going through is a
    real consequence of confirming every clear, not a weakened test: in this
    scenario nothing SHOULD clear. The gate's permissiveness is isolated in the
    unit tests, where ground truth can be told to agree the book is free
    (test_the_gate_clears_a_mark_older_than_the_index_currency). It is also
    direct evidence for the open question of whether the gate is now redundant
    — see the PR's clear-direction section.
    """
    monkeypatch.setenv("OL_SOLR_BASE_URL", SOLR)
    _seed_one_edition()
    _set_index([])  # the index believes nothing is checked out
    _set_feed(
        [
            {
                "identifier": FRESH_OCAID,
                "uid": 100,
                "event_type": "borrow",
                "extra": "{}",
                # Five seconds ago, not "now": the mark is stamped from the EVENT time,
                # and the tight-margin half of this test needs the stamp to be
                # provably older than (poll time - margin) rather than within a
                # fraction of a second of it. A test that depends on which side of a
                # sub-second boundary two clocks land is a flake, not a check.
                "time": (datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
    )

    asyncio.run(_feed_once())
    _commit()
    doc = _edition(FRESH_EDITION)
    assert doc.get("ebook_unavailable") == 1, "the feed must mark a borrow the index has not seen"
    assert doc.get("ebook_unavailable_ts"), "a mark with no stamp cannot be protected by the gate"

    # A day-sized margin: the mark is far newer than the index's currency.
    spy = asyncio.run(_poll_once(margin=86_400))
    _commit()
    assert _edition(FRESH_EDITION).get("ebook_unavailable") == 1, "a poll must not clear a mark the index is too stale to contradict"
    assert spy.call_count == 0, "the gate must have removed it before the confirmation stage, so ground truth was never asked"

    # One second: the index is treated as current, so the gate stops protecting
    # the mark and the clear reaches ground truth -- which says the book is
    # still out, because it is.
    spy = asyncio.run(_poll_once(margin=1))
    _commit()
    assert spy.call_count == 1, "the gate must have let this one through to the confirmation stage"
    # MEMBERSHIP, not equality. These tests share one Solr core, so marks left
    # by the others are still there and the poll legitimately proposes clearing
    # them too. An equality assertion here passed or failed on test ORDER --
    # measured flaking about one run in four.
    assert FRESH_EDITION in [doc["key"] for doc in spy.call_args.args[0]], "and this edition is among those proposed for clearing"
    # The two together are the finding: the clear WAS proposed and the book is
    # STILL marked, so the confirmation stage is what held it.
    assert _edition(FRESH_EDITION).get("ebook_unavailable") == 1, "a book borrowed five seconds ago stays marked, whichever layer says so"

    # Put the shared fixture back: a staged window is frozen, and leaving it
    # frozen poisons every later test against this container.
    _reset_feed()
