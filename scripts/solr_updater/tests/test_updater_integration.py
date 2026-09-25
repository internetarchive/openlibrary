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
"""

import json
import os
import signal
import urllib.error
import urllib.request

import pytest

from scripts.solr_updater.loan_availability_updater import main

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
    head = json.load(urllib.request.urlopen(f"{FEED}/services/loans/loan/?action=changes&after_uid=0&limit=1", timeout=10))
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

    head = json.load(urllib.request.urlopen(f"{FEED}/services/loans/loan/?action=changes&after_uid=0&limit=1", timeout=10))
    state = tmp_path / "state"
    state.write_text(str(max(1, (head.get("latest_uid") or 0) - 200)))

    def stop(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGALRM, stop)
    signal.alarm(30)
    try:
        with pytest.raises(SystemExit):
            main("conf/openlibrary.yml", state_file=str(state), poll_interval=2, recheck_interval=5)
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
