"""Run the real daemon against a real Solr and a real changes feed.

Replaces an 878-line standalone harness that reimplemented the updater's logic
so a reviewer could watch it, plus a 92-line guard whose only job was keeping
that copy in sync with the original. The copy drifted anyway -- it went on
demonstrating an availability join after the daemon stopped performing one --
and a guard against drift between a thing and its copy is a copy-shaped
problem.

This exercises `main()` itself, which is what matters: the worst defect this
change ever had was a cold start that could never complete against production's
`maxBooleanClauses`, and it survived 8/8 green CI because nothing had executed
the daemon anywhere.

Skipped unless both services are reachable, so it is a no-op in CI and a real
check locally. To run it:

    docker compose up -d --no-build mockservices
    docker run -d --name ol-test-solr -p 8984:8983 \\
      -v "$(pwd)/conf/solr:/opt/solr/server/solr/configsets/olconfig:ro" \\
      -e SOLR_MODULES=analysis-extras \\
      solr:10.0.0 solr-precreate openlibrary \\
      /opt/solr/server/solr/configsets/olconfig

    SOLR_URL=http://localhost:8984/solr/openlibrary \\
    MOCKSERVICES_URL=http://localhost:8090 \\
    pytest scripts/solr_updater/tests/test_updater_integration.py

Triaging a red run here. Both tests read a live mock whose state moves, so each
has a race mode, and each names itself in its assertion message:

* "the index reported nothing checked out" -- the mock's rolling window held no
  checked-out identifier at the instant the seed was read.
* "daemon completed cycles but wrote nothing" -- the feed emitted no followed
  event inside its window, which the other test's docstring documents.

Capture the assertion message before re-running, because a bare pass/fail count
cannot tell you which. One failure of unknown identity was observed on
2026-10-03 and never reproduced: 21 runs of this file against Solr 10.0.0 and
mockservices, 20 green, including a dedicated 12-run batch afterwards that
captured failure text and caught nothing. It is unexplained rather than benign
-- a red here is worth reading, not worth re-running past.
"""

import asyncio
import json
import os
import signal
import urllib.error
import urllib.request

import pytest

from infogami import config
from openlibrary.config import load_config
from openlibrary.utils.request_context import create_context_for_script, req_context
from scripts.solr_updater.loan_availability_updater import main, run_cold_start

SOLR = os.environ.get("SOLR_URL", "http://localhost:8984/solr/openlibrary")
FEED = os.environ.get("MOCKSERVICES_URL", "http://localhost:8090")

WORK_PREFIX, EDITION_PREFIX = "/works/OL7700", "/books/OL7700"


def _reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=3).read()
        return True
    except urllib.error.URLError, OSError:
        return False


pytestmark = pytest.mark.skipif(
    not (_reachable(f"{SOLR}/admin/ping") and _reachable(f"{FEED}/health")),
    reason="needs a Solr and a mockservices feed; see this module's docstring",
)


def _post(path: str, payload) -> dict:
    req = urllib.request.Request(f"{SOLR}/{path}", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def _edition(key: str) -> dict:
    return json.load(urllib.request.urlopen(f"{SOLR}/get?id={key}&wt=json", timeout=10)).get("doc") or {}


@pytest.fixture
def seeded_editions():
    """An edition for every ocaid the feed is currently circulating.

    Seeding one ocaid is not enough and made this flaky: the daemon cold-starts
    near the feed head, so whether one particular identifier shows up in the
    events of a short window is luck. The mock feed cycles a small pool, so
    seeding the whole pool makes "did the daemon write anything real" a
    deterministic question.
    """
    head = json.load(urllib.request.urlopen(f"{FEED}/services/loans/loan/?action=changes&after_uid=1&limit=1", timeout=10))
    after = max(0, (head.get("latest_uid") or 0) - 200)
    rows = json.load(urllib.request.urlopen(f"{FEED}/services/loans/loan/?action=changes&after_uid={after}&limit=200", timeout=10))["rows"]
    ocaids = sorted({r["identifier"] for r in rows if r.get("identifier")})
    assert ocaids, "the feed produced no identifiers; is mockservices seeded?"

    docs = [
        {
            "key": f"{WORK_PREFIX}{i}W",
            "type": "work",
            "title": f"Integration {i}",
            "editions": [{"key": f"{EDITION_PREFIX}{i}M", "type": "edition", "work_key": [f"{WORK_PREFIX}{i}W"], "ia": [ocaid]}],
        }
        for i, ocaid in enumerate(ocaids)
    ]
    _post("update", docs)
    urllib.request.urlopen(f"{SOLR}/update?commit=true", timeout=30).read()
    return [f"{EDITION_PREFIX}{i}M" for i in range(len(ocaids))]


def test_the_daemon_marks_a_borrowed_book(seeded_editions, tmp_path, monkeypatch):
    """Follow real events through main() to a real Solr write.

    The cursor is pre-seeded behind the feed head so there is a known backlog
    waiting. Without that this was flaky twice over: `loan_uid` is written only
    by the follower, the mock feed emits in bursts, and whether a burst lands
    inside the window is luck. Starting behind the head makes the work already
    exist when the daemon opens its eyes.

    Bounded by SIGALRM rather than a row count: main() is an infinite loop by
    design, and anything that stops it early -- a mocked feed running dry --
    would also mask the loop bugs this exists to catch.
    """
    monkeypatch.setenv("OL_SOLR_BASE_URL", SOLR)

    head = json.load(urllib.request.urlopen(f"{FEED}/services/loans/loan/?action=changes&after_uid=1&limit=1", timeout=10))
    state = tmp_path / "state"
    state.write_text(str(max(1, (head.get("latest_uid") or 0) - 200)))

    def stop(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGALRM, stop)
    signal.alarm(30)
    try:
        with pytest.raises(SystemExit):
            asyncio.run(main("conf/openlibrary.yml", state_file=str(state), poll_interval=2, recheck_interval=5))
    finally:
        signal.alarm(0)

    docs = [_edition(key) for key in seeded_editions]
    assert all(docs), "seeded editions vanished from Solr"
    # Which editions get written depends on what the live feed did during those
    # seconds, so this asserts on the population rather than on one document.
    # `loan_uid` only ever appears if an event was followed all the way through
    # to a Solr write, so its presence is proof the whole path ran.
    written = [d for d in docs if "loan_uid" in d]
    assert written, f"daemon completed cycles but wrote nothing across {len(docs)} seeded editions"
    assert all(d.get("ebook_unavailable") in (0, 1, None) for d in written)


def test_a_cold_start_seeds_from_the_index_and_lands_the_cursor_at_the_head(monkeypatch):
    """The other test pre-seeds the cursor, so main() takes the steady-state
    path and never calls run_cold_start -- its green says nothing about the
    seed. This runs the cold start itself against a real Solr and a real
    endpoint: index query, ground truth, overlap replay, cursor returned.

    It calls run_cold_start directly rather than through main(), because
    through main() the cursor cannot be judged at all: the daemon enters steady
    state immediately afterwards and, against a feed this small, follows its
    way to the head within any sane time budget whatever the cold start
    returned. Reading the real function's return value is the only way to see
    where the cold start actually put the cursor.

    What this kills, measured by mutation: deleting the overlap replay
    (`return 1` in place of the call) turns it red. What it does NOT kill, also
    measured, and both for reasons about the mock rather than the daemon:

    * Removing the `uid = head` line that places the cursor when the feed has
      nothing left. That line is only reachable when a page comes back with
      zero rows, and the mock always has rows, so no end-to-end run against it
      can enter that branch. It is unit-covered.
    * Removing the seed's Solr write. The mock derives checked-out status from
      the same rolling event window it serves as the feed, so the replay marks
      the same books the seed would have, and this stays green. Deleting that
      write reddens two unit tests.

    It also does not assert that any mark was written, which is a race: the
    window moves between the index read and the availability call, and this was
    observed marking 0 of 2 identifiers on one run and several on the next.

    So: an honest smoke test that the whole cold start completes against real
    services and advances the cursor to the head, not a substitute for the unit
    tests that isolate its parts.
    """
    monkeypatch.setenv("OL_SOLR_BASE_URL", SOLR)

    # Editions for whatever the index currently calls checked out, so the seed
    # has real identifiers to resolve rather than an empty candidate list.
    checked_out = json.load(
        urllib.request.urlopen(
            f"{FEED}/advancedsearch.php?q=lending___is_lendable%3Atrue+AND+lending___available_to_borrow%3Afalse"
            f"+AND+lending___available_to_browse%3Afalse&rows=1000&page=1&output=json",
            timeout=10,
        )
    )["response"]["docs"]
    ocaids = sorted({d["identifier"] for d in checked_out if d.get("identifier")})
    assert ocaids, "the index reported nothing checked out; the seed would be vacuous"

    _post(
        "update",
        [
            {
                "key": f"{WORK_PREFIX}9{i}W",
                "type": "work",
                "title": f"Cold start {i}",
                "editions": [{"key": f"{EDITION_PREFIX}9{i}M", "type": "edition", "work_key": [f"{WORK_PREFIX}9{i}W"], "ia": [ocaid]}],
            }
            for i, ocaid in enumerate(ocaids)
        ],
    )
    urllib.request.urlopen(f"{SOLR}/update?commit=true", timeout=30).read()

    head = (json.load(urllib.request.urlopen(f"{FEED}/services/loans/loan/?action=changes&after_uid=1&limit=1", timeout=10)).get("latest_uid")) or 0
    assert head, "the feed reported no head; cannot judge where the cursor landed"

    cursor = asyncio.run(_cold_start())

    assert cursor >= head, f"cold start returned cursor {cursor}, behind the head {head} the overlap replay should have reached"

    # Nothing may carry a value other than the marked sentinel. Cheap, and it
    # catches a write path that puts something else in the field.
    for i in range(len(ocaids)):
        value = _edition(f"{EDITION_PREFIX}9{i}M").get("ebook_unavailable")
        assert value in (0, 1, None), f"unexpected ebook_unavailable {value!r}"


async def _cold_start() -> int:
    """run_cold_start inside the same script request context main() sets up."""
    if not config.get("plugin_openlibrary"):
        load_config("conf/openlibrary.yml")
    token = req_context.set(create_context_for_script())
    try:
        return await run_cold_start(poll_interval=2, dry_run=False)
    finally:
        req_context.reset(token)
