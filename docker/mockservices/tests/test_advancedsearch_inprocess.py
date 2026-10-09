"""The mock AdvancedSearch endpoint over real HTTP, with no container required.

This endpoint is the loan availability updater's whole input, so its contract is
checked where CI runs; ``make test-py`` starts no containers, which leaves the
tests in ``test_e2e.py`` skipped there.

Served with ``lifespan="off"``, so the startup seeder (and its Solr calls) stay
out of it and every test states its own set.
"""

import importlib.util
import pathlib
import threading
import time
import urllib.parse

import pytest
import requests

MOCKSERVICES_MAIN = pathlib.Path(__file__).parents[1] / "main.py"

CHECKED_OUT_QUERY = "lending___is_lendable:true AND lending___available_to_borrow:false AND lending___available_to_browse:false"


def _load_mock_app_module():
    spec = importlib.util.spec_from_file_location("ol_mockservices_main_advancedsearch", MOCKSERVICES_MAIN)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"could not load {MOCKSERVICES_MAIN}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def base_url():
    mock_module = _load_mock_app_module()
    uvicorn = pytest.importorskip("uvicorn", reason="uvicorn is needed to serve the mock in-process")
    pytest.importorskip("fastapi", reason="fastapi is needed to build the mock app")

    config = uvicorn.Config(mock_module.app, host="127.0.0.1", port=0, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 30
    while not server.started:
        if not thread.is_alive():  # pragma: no cover
            pytest.fail("mock advancedsearch server thread died during startup")
        if time.monotonic() > deadline:  # pragma: no cover
            server.should_exit = True
            pytest.fail("mock advancedsearch server did not start within 30s")
        time.sleep(0.05)

    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)


def _set_unavailable(base_url: str, identifiers: list[str]) -> None:
    response = requests.put(f"{base_url}/_test/unavailable", json={"identifiers": identifiers}, timeout=10)
    response.raise_for_status()


def _search(base_url: str, **params) -> dict:
    query = urllib.parse.urlencode({"q": CHECKED_OUT_QUERY, "output": "json", **params})
    response = requests.get(f"{base_url}/advancedsearch.php?{query}", timeout=10)
    response.raise_for_status()
    return response.json()


def test_the_set_a_test_puts_is_the_set_the_search_returns(base_url):
    _set_unavailable(base_url, ["bookccc", "bookaaa", "bookbbb"])
    body = _search(base_url, rows=100, page=1)
    assert body["response"]["numFound"] == 3
    assert [doc["identifier"] for doc in body["response"]["docs"]] == ["bookaaa", "bookbbb", "bookccc"]


def test_the_set_can_change_between_two_reads(base_url):
    """A book returned between polls leaves the set; a book borrowed joins it."""
    _set_unavailable(base_url, ["bookaaa", "bookbbb"])
    first = {doc["identifier"] for doc in _search(base_url, rows=100, page=1)["response"]["docs"]}
    _set_unavailable(base_url, ["bookbbb", "bookccc"])
    second = {doc["identifier"] for doc in _search(base_url, rows=100, page=1)["response"]["docs"]}
    assert first == {"bookaaa", "bookbbb"}
    assert second == {"bookbbb", "bookccc"}


def test_an_empty_set_is_reported_as_empty_rather_than_withheld(base_url):
    _set_unavailable(base_url, [])
    body = _search(base_url, rows=100, page=1)
    assert body["response"]["numFound"] == 0
    assert body["response"]["docs"] == []


def test_paging_walks_the_set_without_repeating_or_skipping(base_url):
    _set_unavailable(base_url, [f"book{i:03d}" for i in range(25)])
    seen: list[str] = []
    for page in range(1, 4):
        body = _search(base_url, rows=10, page=page)
        assert body["response"]["start"] == (page - 1) * 10
        seen += [doc["identifier"] for doc in body["response"]["docs"]]
    assert seen == sorted(f"book{i:03d}" for i in range(25))


def test_numfound_describes_the_set_not_the_page(base_url):
    """numFound is the whole set, not the page; the daemon's completeness check relies on it."""
    _set_unavailable(base_url, [f"book{i:03d}" for i in range(25)])
    body = _search(base_url, rows=10, page=1)
    assert body["response"]["numFound"] == 25
    assert len(body["response"]["docs"]) == 10


def test_a_request_past_the_window_omits_the_response_envelope(base_url):
    """Like the real endpoint, past `start + rows <= 10000` it answers HTTP 200 with no `response` key."""
    _set_unavailable(base_url, ["bookaaa"])
    body = _search(base_url, rows=1000, page=11)
    assert "response" not in body


def test_a_query_the_mock_does_not_understand_answers_nothing(base_url):
    _set_unavailable(base_url, ["bookaaa"])
    query = urllib.parse.urlencode({"q": "collection:inlibrary", "output": "json", "rows": 100})
    body = requests.get(f"{base_url}/advancedsearch.php?{query}", timeout=10).json()
    assert body["response"]["numFound"] == 0
    assert _search(base_url, rows=100, page=1)["response"]["numFound"] == 1, "control: the real query still answers"


def test_a_malformed_control_request_is_rejected(base_url):
    response = requests.put(f"{base_url}/_test/unavailable", json={"identifiers": "not-a-list"}, timeout=10)
    assert response.status_code == 400
