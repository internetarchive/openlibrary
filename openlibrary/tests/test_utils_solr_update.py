"""Tests for Solr.update_async / Solr.update in openlibrary/utils/solr.py"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from openlibrary.utils.solr import Solr


def _ok_response(body=None):
    """Return a mock httpx.Response that succeeds."""
    body = body or {"responseHeader": {"status": 0, "QTime": 1}}
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = 200
    mock.json.return_value = body
    mock.raise_for_status = MagicMock()  # no-op — 200 is fine
    return mock


def _error_response(status_code=400, text="error"):
    """Return a mock httpx.Response that raises on raise_for_status."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.json.return_value = {"responseHeader": {"status": status_code}}
    mock.raise_for_status.side_effect = httpx.HTTPStatusError(text, request=MagicMock(), response=mock)
    return mock


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def solr():
    s = Solr("http://localhost:8983/solr/openlibrary")
    s.async_session = AsyncMock()
    return s


# ---------------------------------------------------------------------------
# URL correctness
# ---------------------------------------------------------------------------


def test_update_posts_to_correct_url_no_requireinplace(solr):
    solr.async_session.post.return_value = _ok_response()
    _run(solr.update_async([{"key": "/works/OL1W", "ebook_availability": {"set": "available"}}]))
    url = solr.async_session.post.call_args[0][0]
    assert "/update" in url
    assert "requireInPlace" not in url
    assert "wt=json" in url


def test_update_does_not_use_requireinplace_for_commit_either(solr):
    solr.async_session.post.return_value = _ok_response()
    _run(solr.update_async([], commit=True))
    url = solr.async_session.post.call_args[0][0]
    assert "requireInPlace" not in url


# ---------------------------------------------------------------------------
# Error raising
# ---------------------------------------------------------------------------


def test_update_raises_on_http_400(solr):
    solr.async_session.post.return_value = _error_response(400)
    with pytest.raises(httpx.HTTPStatusError):
        _run(solr.update_async([{"key": "/works/OL1W", "ebook_availability": {"set": "x"}}]))


def test_update_raises_on_nonzero_response_header_status(solr):
    # Solr can return HTTP 200 but with a non-zero status in the body
    bad_body = {"responseHeader": {"status": 1, "QTime": 0}, "error": {"msg": "oops"}}
    solr.async_session.post.return_value = _ok_response(body=bad_body)
    with pytest.raises(RuntimeError, match="Solr update error"):
        _run(solr.update_async([{"key": "/works/OL1W", "ebook_availability": {"set": "x"}}]))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_update_happy_path_does_not_raise(solr):
    solr.async_session.post.return_value = _ok_response()
    _run(solr.update_async([{"key": "/works/OL1W", "ebook_availability": {"set": "available"}}]))  # no exception


def test_update_returns_none(solr):
    solr.async_session.post.return_value = _ok_response()
    result = _run(solr.update_async([{"key": "/works/OL1W", "ebook_availability": {"set": "available"}}]))
    assert result is None


# ---------------------------------------------------------------------------
# Commit behaviour
# ---------------------------------------------------------------------------


def test_update_commit_true_sends_two_posts(solr):
    """commit=True with a non-empty request sends update POST then commit POST."""
    solr.async_session.post.return_value = _ok_response()
    _run(
        solr.update_async(
            [{"key": "/works/OL1W", "ebook_availability": {"set": "available"}}],
            commit=True,
        )
    )
    assert solr.async_session.post.call_count == 2
    # Second call must send the commit payload
    second_call_kwargs = solr.async_session.post.call_args_list[1]
    assert second_call_kwargs.kwargs["json"] == {"commit": {}}


def test_update_empty_request_commit_true_sends_only_commit_post(solr):
    """Empty list + commit=True must skip the update POST and only commit."""
    solr.async_session.post.return_value = _ok_response()
    _run(solr.update_async([], commit=True))
    assert solr.async_session.post.call_count == 1
    call_kwargs = solr.async_session.post.call_args.kwargs
    assert call_kwargs["json"] == {"commit": {}}


def test_update_empty_request_commit_false_sends_no_posts(solr):
    """Empty list + commit=False is a no-op — nothing sent to Solr."""
    _run(solr.update_async([], commit=False))
    solr.async_session.post.assert_not_called()


def test_update_commit_false_sends_one_post(solr):
    """commit=False sends exactly one POST (the update, no commit)."""
    solr.async_session.post.return_value = _ok_response()
    _run(
        solr.update_async(
            [{"key": "/works/OL1W", "ebook_availability": {"set": "available"}}],
            commit=False,
        )
    )
    assert solr.async_session.post.call_count == 1


def test_update_commit_raises_on_error(solr):
    """If the commit POST returns an error, it should raise."""
    ok = _ok_response()
    err = _error_response(500)
    solr.async_session.post.side_effect = [ok, err]
    with pytest.raises(httpx.HTTPStatusError):
        _run(
            solr.update_async(
                [{"key": "/works/OL1W", "ebook_availability": {"set": "available"}}],
                commit=True,
            )
        )
