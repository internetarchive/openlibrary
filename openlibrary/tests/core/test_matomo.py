"""Tests for the read-only Matomo client used by Core Vitals retention scoring."""

import datetime
from unittest.mock import Mock, patch

import pytest
import requests

from openlibrary.core.matomo import MatomoClient, MatomoError, MatomoMethodNotAllowed


def _response(payload, status_code: int = 200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _client(**kwargs) -> MatomoClient:
    return MatomoClient("tok", **kwargs)


def _patch_post(client, **kwargs):
    """Patch the client's own session, which is what issues requests."""
    return patch.object(client._session, "post", **kwargs)


class TestReadOnlyAllowlist:
    @pytest.mark.parametrize(
        "method",
        [
            "SitesManager.deleteSite",
            "UsersManager.setUserAccess",
            "Goals.addGoal",
            "AnythingElse.get",
            # Prefix matching allowed this: it sits under "API." but tunnels
            # arbitrary methods via its `urls[]` parameter.
            "API.getBulkRequest",
            # These were allowed by the old prefix list but are not used here.
            "VisitsSummary.get",
            "Events.getCategory",
        ],
    )
    def test_rejects_anything_not_exactly_allowlisted(self, method):
        with pytest.raises(MatomoMethodNotAllowed, match="read-only allowlist"):
            _client()._post(method)

    def test_a_disallowed_method_is_distinguishable_from_a_flaky_matomo(self):
        """A caller degrading gracefully on MatomoError must not swallow a programming error."""
        assert issubclass(MatomoMethodNotAllowed, MatomoError)

    def test_blocks_before_any_network_call_is_made(self):
        client = _client()
        with _patch_post(client) as mock_post, pytest.raises(MatomoMethodNotAllowed):
            client._post("SitesManager.deleteSite")
        mock_post.assert_not_called()

    def test_allows_the_one_method_this_codebase_uses(self):
        client = _client()
        with _patch_post(client, return_value=_response([])):
            assert client._post("Live.getLastVisitsDetails") == []

    def test_requires_a_token(self):
        """A missing token is a caller bug, not Matomo being unreachable."""
        with pytest.raises(ValueError, match="token is required"):
            MatomoClient("")


class TestTokenHandling:
    def test_token_is_sent_in_the_post_body_not_the_url(self):
        """The token must never land in a query string, where proxies and access logs record it."""
        client = MatomoClient("s3cret")
        with _patch_post(client, return_value=_response([])) as mock_post:
            client._post("Live.getLastVisitsDetails")

        url = mock_post.call_args.args[0]
        assert "s3cret" not in url
        assert mock_post.call_args.kwargs["data"]["token_auth"] == "s3cret"
        assert "params" not in mock_post.call_args.kwargs

    # `method` is not in this list because it is a positional parameter of
    # `_post`, so it cannot be smuggled in via **params at all.
    @pytest.mark.parametrize("key", ["token_auth", "module", "idSite", "format"])
    def test_a_caller_cannot_override_the_fixed_keys(self, key):
        """Params are applied before the fixed keys, so nothing can redirect the request."""
        client = MatomoClient("real-token", site_id=6)
        with _patch_post(client, return_value=_response([])) as mock_post:
            client._post("Live.getLastVisitsDetails", **{key: "hijacked"})

        sent = mock_post.call_args.kwargs["data"]
        assert sent[key] != "hijacked"
        assert sent["token_auth"] == "real-token"
        assert sent["module"] == "API"
        assert sent["idSite"] == 6

    def test_the_token_does_not_appear_in_error_messages(self):
        client = MatomoClient("s3cret")
        with _patch_post(client, side_effect=requests.ConnectionError("no route")), pytest.raises(MatomoError) as excinfo:
            client._post("Live.getLastVisitsDetails")
        assert "s3cret" not in str(excinfo.value)

    def test_posts_to_the_index_php_endpoint(self):
        client = _client(url="https://matomo.example.org/")
        with _patch_post(client, return_value=_response([])) as mock_post:
            client._post("Live.getLastVisitsDetails")
        assert mock_post.call_args.args[0] == "https://matomo.example.org/index.php"


class TestErrorHandling:
    def test_wraps_network_failures(self):
        client = _client()
        with _patch_post(client, side_effect=requests.ConnectionError("no route")), pytest.raises(MatomoError, match="request failed"):
            client._post("Live.getLastVisitsDetails")

    def test_raises_on_matomo_api_error_payload(self):
        client = _client()
        payload = {"result": "error", "message": "Invalid token_auth"}
        with _patch_post(client, return_value=_response(payload)), pytest.raises(MatomoError, match="Invalid token_auth"):
            client._post("Live.getLastVisitsDetails")

    def test_raises_on_non_json_response(self):
        client = _client()
        response = _response(None)
        response.json.side_effect = ValueError("not json")
        with _patch_post(client, return_value=response), pytest.raises(MatomoError, match="non-JSON"):
            client._post("Live.getLastVisitsDetails")


class TestWindowBounds:
    def test_rejects_a_window_longer_than_matomo_will_serve(self):
        """`date` is derived from `since`, but Matomo's raw retention is finite."""
        client = _client()
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)
        with pytest.raises(ValueError, match="longer than"):
            client.get_visits_since(since)

    def test_rejects_a_future_since(self):
        client = _client()
        with pytest.raises(ValueError, match="in the future"):
            client.get_visits_since(datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1))

    def test_the_date_range_covers_the_requested_window(self):
        """A fixed `date=last7` silently clamped anything longer to seven days.

        The range is padded a day either side because Matomo reads `date` in the
        site's timezone while `since` is UTC -- an exact range dropped the
        earliest hour entirely against the real instance.
        """
        client = _client()
        now = datetime.datetime.now(datetime.UTC)
        since = now - datetime.timedelta(days=3)
        with patch.object(client, "_post", return_value=[]) as mock_post:
            client.get_visits_since(since)

        start, _, end = mock_post.call_args.kwargs["date"].partition(",")
        assert datetime.date.fromisoformat(start) < since.date()
        assert datetime.date.fromisoformat(end) > now.date()


class TestGetVisitsSince:
    def test_paginates_until_an_empty_page(self):
        client = _client()
        pages = [
            [{"idVisit": i} for i in range(3)],
            [{"idVisit": i} for i in range(3, 6)],
            [],
        ]
        with patch.object(client, "_post", side_effect=pages) as mock_post:
            fetch = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=3)

        assert [v["idVisit"] for v in fetch.visits] == list(range(6))
        assert mock_post.call_count == 3

    def test_a_short_page_does_not_end_pagination(self):
        """Matomo enforces server-side row caps, so a page can be shorter than asked.

        Treating that as the end of the feed silently truncated the score.
        """
        client = _client()
        pages = [
            [{"idVisit": i} for i in range(100)],
            [{"idVisit": i} for i in range(100, 150)],
            [],
        ]
        with patch.object(client, "_post", side_effect=pages):
            fetch = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=500)
        assert len(fetch.visits) == 150
        assert fetch.truncated is False

    def test_offset_follows_what_was_actually_received(self):
        """Stepping by page*page_size skips records whenever a page comes back short."""
        client = _client()
        pages = [[{"idVisit": i} for i in range(10)], []]
        with patch.object(client, "_post", side_effect=pages) as mock_post:
            client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=500)
        assert [call.kwargs["filter_offset"] for call in mock_post.call_args_list] == [0, 10]

    def test_duplicate_visits_across_pages_are_dropped(self):
        """The feed is live and newest-first, so pages overlap as visits arrive."""
        client = _client()
        pages = [
            [{"idVisit": 1}, {"idVisit": 2}, {"idVisit": 3}],
            [{"idVisit": 3}, {"idVisit": 4}],
            [],
        ]
        with patch.object(client, "_post", side_effect=pages):
            fetch = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=3)
        assert [v["idVisit"] for v in fetch.visits] == [1, 2, 3, 4]

    def test_a_live_feed_shifting_by_a_full_page_loses_nothing(self):
        """Regression: an all-duplicate page means the window moved, not that the feed ended.

        The feed is newest-first and live. If enough visits arrive between two
        requests, the next offset lands entirely on rows already consumed.
        Treating that as end-of-feed dropped everything past the shift and
        reported `truncated=False` -- a silently short score.
        """
        client = _client()
        state = {"n": 0}

        def growing_feed(_method, **kw):
            state["n"] += 1
            # Five new visits land after the first page and remain thereafter.
            feed = list(range(15, 0, -1)) if state["n"] >= 2 else list(range(10, 0, -1))
            offset, limit = kw["filter_offset"], kw["filter_limit"]
            return [{"idVisit": str(v)} for v in feed[offset : offset + limit]]

        with patch.object(client, "_post", side_effect=growing_feed):
            fetch = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=5)

        collected = {int(v["idVisit"]) for v in fetch.visits}
        assert set(range(1, 11)) <= collected, "lost visits past the window shift"
        assert len(fetch.visits) == len(collected), "returned duplicates"

    def test_the_offset_tracks_rows_served_not_rows_kept(self):
        """Offsetting by the deduped count re-requests rows already consumed."""
        client = _client()
        pages = [
            [{"idVisit": 1}, {"idVisit": 2}],
            [{"idVisit": 2}, {"idVisit": 3}],  # one duplicate
            [],
        ]
        with patch.object(client, "_post", side_effect=pages) as mock_post:
            client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=2)
        # 0, then 2 (rows served), then 4 -- not 0, 2, 3 (rows kept).
        assert [call.kwargs["filter_offset"] for call in mock_post.call_args_list] == [0, 2, 4]

    def test_an_empty_page_ends_pagination(self):
        client = _client()
        pages = [[{"idVisit": 1}], [{"idVisit": 1}], []]
        with patch.object(client, "_post", side_effect=pages) as mock_post:
            fetch = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=1)
        assert len(fetch.visits) == 1
        assert mock_post.call_count == 3

    def test_passes_min_timestamp(self):
        client = _client()
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
        with patch.object(client, "_post", return_value=[]) as mock_post:
            client.get_visits_since(since)
        assert mock_post.call_args.kwargs["minTimestamp"] == int(since.timestamp())

    @pytest.mark.parametrize("payload", [{"unexpected": "dict"}, {}, "a string", 42])
    def test_a_non_list_payload_is_an_error_not_an_empty_feed(self, payload):
        """An empty dict is falsy: checking emptiness first would read it as end-of-feed."""
        client = _client()
        with _patch_post(client, return_value=_response(payload)), pytest.raises(MatomoError, match="expected a list of rows"):
            client._post("Live.getLastVisitsDetails")

    def test_the_page_cap_reports_truncation(self):
        """A truncated window must not be reported as a quiet one."""
        client = _client()
        with patch.object(client, "_post", side_effect=lambda *a, **k: [{"idVisit": f"{k['filter_offset']}-{n}"} for n in range(2)]):
            fetch = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=2)
        assert fetch.truncated is True
        assert "page cap" in fetch.truncated_reason

    def test_the_time_budget_reports_truncation(self):
        """`timeout` is per socket read and bounds no overall duration."""
        client = _client()
        with patch.object(client, "_post", return_value=[{"idVisit": 1}]) as mock_post:
            fetch = client.get_visits_since(datetime.datetime.now(datetime.UTC), budget_seconds=0)
        assert fetch.truncated is True
        assert "budget" in fetch.truncated_reason
        assert fetch.visits == []
        mock_post.assert_not_called()

    def test_the_budget_is_per_call_not_per_client(self):
        """It bounds one fetch, so a client is not permanently poisoned by a tight budget."""
        client = _client()
        with patch.object(client, "_post", return_value=[]):
            assert client.get_visits_since(datetime.datetime.now(datetime.UTC), budget_seconds=0).truncated is True
            assert client.get_visits_since(datetime.datetime.now(datetime.UTC), budget_seconds=300).truncated is False

    def test_a_clean_run_is_not_flagged_truncated(self):
        client = _client()
        with patch.object(client, "_post", return_value=[]):
            fetch = client.get_visits_since(datetime.datetime.now(datetime.UTC))
        assert fetch.truncated is False
        assert fetch.truncated_reason is None
