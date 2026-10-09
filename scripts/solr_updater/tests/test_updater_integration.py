"""Run the real poll loop (`main()`) against a real Solr and the mock index.

The mock's unavailable set can be changed between polls, so returns, borrows
and reindex wipes are staged rather than raced for.

Skipped unless both services are reachable. To run it:

    docker compose up -d --no-build mockservices solr
    docker compose run --rm --no-deps \\
      -e SOLR_URL=http://solr:8983/solr/openlibrary \\
      -e MOCKSERVICES_URL=http://mockservices:8090 \\
      home python -m pytest scripts/solr_updater/tests/test_updater_integration.py

The tests run inside the compose network, so Solr's host port isn't needed; if
8983 is taken, start Solr without publishing it:

    printf 'services:\\n  solr:\\n    ports: !reset []\\n' > .solr-noport.yaml
    docker compose -f compose.yaml -f .solr-noport.yaml up -d --no-build solr

Another project's container on the same network can hold the `solr` alias; if
so, point SOLR_URL at your own container's IP:

    docker inspect <project>-solr-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
"""

import asyncio
import datetime
import itertools
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


def _put(path: str, payload: dict) -> None:
    req = urllib.request.Request(
        f"{FEED}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    urllib.request.urlopen(req, timeout=10).read()


_index_clock = itertools.count()


def _set_index(identifiers: list[str], dated: bool = True) -> None:
    """Replace what the mock index calls checked out.

    `dated` also stages a loan-event time, since the clear gate only clears
    marks older than the index's newest event. Each call advances that time by
    a minute: the gate compares whole seconds, so two calls in the same second
    would leave the first poll's marks not strictly older and never cleared.
    `dated=False` stages books with no times at all, which must clear nothing.
    """
    _put("/_test/unavailable", {"identifiers": identifiers})
    stamp = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=next(_index_clock))).strftime("%Y-%m-%dT%H:%M:%SZ")
    _put("/_test/loan_event_times", {i: {"lending___last_browse": stamp} for i in identifiers} if dated else {})


@pytest.fixture
def seeded_editions():
    """Six editions, one per ocaid, with no availability field.

    Posted as full documents, as a reindex writes them, so calling it again
    wipes the field the way a reindex does.
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
    """Run main()'s real loop for exactly one cycle, stopped at the end-of-cycle
    sleep rather than by a timeout that could interrupt the write."""
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

    # Unit tests mock Solr, so only this catches the schema rejecting or not
    # declaring `ebook_unavailable_ts`. Bounded by the clock so milliseconds or
    # a frozen value fail.
    now = int(time.time())
    for key in marked:
        ts = _edition(key).get("ebook_unavailable_ts")
        assert ts is not None, f"{key} is marked but carries no ebook_unavailable_ts; is the field declared in the schema?"
        assert now - 300 <= ts <= now + 60, f"{key} ts={ts} is not epoch seconds near now ({now})"


def test_a_poll_clears_a_book_the_index_has_released(seeded_editions, monkeypatch):
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
    # requireInPlace cannot null a field, so a clear leaves the stamp behind --
    # a claim about Solr's behaviour, hence checked against a real Solr.
    assert _edition(keys[1]).get("ebook_unavailable_ts") is not None, "a clear must leave the old stamp in place, not remove it"
    assert _edition(keys[2]).get("ebook_unavailable") == 0, "returned, so freed"


def test_accumulated_cruft_is_reconciled_away_in_one_poll(monkeypatch):
    """Many stale marks (most of the marked set) are all cleared by a single poll."""
    monkeypatch.setenv("OL_SOLR_BASE_URL", SOLR)
    count = 50
    ocaids = [f"cruft{i:03d}" for i in range(count)]
    keys = [f"/books/OL7800{i}M" for i in range(count)]
    _post(
        "update",
        [
            {
                "key": f"/works/OL7800{i}W",
                "type": "work",
                "title": f"Cruft {i}",
                "editions": [{"key": keys[i], "type": "edition", "work_key": [f"/works/OL7800{i}W"], "ia": [ocaids[i]]}],
            }
            for i in range(count)
        ],
    )
    _commit()

    # Mark everything.
    _set_index(ocaids)
    asyncio.run(_one_poll())
    _commit()
    assert sum(_edition(k).get("ebook_unavailable") == 1 for k in keys) == count, "precondition: all marked"

    # The index now reports one; the other 49 must all clear in one poll.
    _set_index(ocaids[:1])
    asyncio.run(_one_poll())
    _commit()

    assert _edition(keys[0]).get("ebook_unavailable") == 1, "the one ES still reports stays marked"
    still_marked = [k for k in keys[1:] if _edition(k).get("ebook_unavailable") != 0]
    assert still_marked == [], f"{len(still_marked)} of 49 stale marks survived the reconcile"


def test_a_mark_with_no_timestamp_is_still_reconciled_away(seeded_editions, monkeypatch):
    """A mark without `ebook_unavailable_ts` is still cleared, not held forever."""
    monkeypatch.setenv("OL_SOLR_BASE_URL", SOLR)
    keys = seeded_editions()

    # A mark with the flag but no stamp.
    _post("update", [{"key": keys[1], "_root_": f"{WORK_PREFIX}1W", "ebook_unavailable": {"set": 1}}])
    _commit()
    assert _edition(keys[1]).get("ebook_unavailable") == 1
    assert _edition(keys[1]).get("ebook_unavailable_ts") is None, "precondition: no stamp, as the old code left it"

    _set_index(OCAIDS[:1])
    asyncio.run(_one_poll())
    _commit()
    assert _edition(keys[1]).get("ebook_unavailable") == 0, "a stampless mark ES does not report must be unset"


def test_a_reindex_wipe_is_repaired_by_the_next_poll(seeded_editions, monkeypatch):
    """A reindex drops `ebook_unavailable`; the next poll restores every mark."""
    monkeypatch.setenv("OL_SOLR_BASE_URL", SOLR)
    keys = seeded_editions()
    _set_index(OCAIDS[:3])
    asyncio.run(_one_poll())
    _commit()
    assert _edition(keys[0]).get("ebook_unavailable") == 1, "precondition: the first poll marked it"

    # Re-post the documents in full, as a reindex does.
    seeded_editions()
    assert _edition(keys[0]).get("ebook_unavailable") is None, "precondition: the field is gone, not zeroed"

    asyncio.run(_one_poll())
    _commit()

    healed = {key for key in keys if _edition(key).get("ebook_unavailable") == 1}
    assert healed == set(keys[:3]), "the next poll must restore every mark with no operator step"
