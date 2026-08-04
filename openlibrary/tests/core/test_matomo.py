"""Tests for the read-only Matomo client used by Core Vitals retention scoring."""

import datetime
from unittest.mock import Mock, patch

import pytest
import requests

from openlibrary.core.matomo import MAX_PAGES, MatomoClient, MatomoError


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
        with pytest.raises(MatomoError, match="BLOCKED"):
            _client()._post(method)

    def test_blocks_before_any_network_call_is_made(self):
        client = _client()
        with _patch_post(client) as mock_post, pytest.raises(MatomoError, match="BLOCKED"):
            client._post("SitesManager.deleteSite")
        mock_post.assert_not_called()

    def test_allows_the_one_method_this_codebase_uses(self):
        client = _client()
        with _patch_post(client, return_value=_response([])):
            assert client._post("Live.getLastVisitsDetails") == []

    def test_requires_a_token(self):
        with pytest.raises(MatomoError, match="token is required"):
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
        with pytest.raises(MatomoError, match="longer than"):
            client.get_visits_since(since)

    def test_rejects_a_future_since(self):
        client = _client()
        with pytest.raises(MatomoError, match="in the future"):
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
            visits = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=3)

        assert [v["idVisit"] for v in visits] == list(range(6))
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
            visits = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=500)
        assert len(visits) == 150
        assert client.truncated is False

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
            visits = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=3)
        assert [v["idVisit"] for v in visits] == [1, 2, 3, 4]

    def test_a_page_of_only_duplicates_ends_pagination(self):
        client = _client()
        pages = [[{"idVisit": 1}], [{"idVisit": 1}]]
        with patch.object(client, "_post", side_effect=pages) as mock_post:
            visits = client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=1)
        assert len(visits) == 1
        assert mock_post.call_count == 2

    def test_passes_min_timestamp(self):
        client = _client()
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
        with patch.object(client, "_post", return_value=[]) as mock_post:
            client.get_visits_since(since)
        assert mock_post.call_args.kwargs["minTimestamp"] == int(since.timestamp())

    def test_rejects_an_unexpected_payload_shape(self):
        client = _client()
        with patch.object(client, "_post", return_value={"unexpected": "dict"}), pytest.raises(MatomoError, match="Expected a list"):
            client.get_visits_since(datetime.datetime.now(datetime.UTC))

    def test_the_page_cap_sets_the_truncated_flag(self):
        """A truncated hour must not be reported as a quiet hour."""
        client = _client()
        page = [{"idVisit": f"p{n}"} for n in range(2)]
        with patch.object(client, "_post", side_effect=lambda *a, **k: [{"idVisit": f"{k['filter_offset']}-{n}"} for n in range(2)]):
            client.get_visits_since(datetime.datetime.now(datetime.UTC), page_size=2)
        assert client.truncated is True
        assert len(page) == 2  # sanity: the stub returns fresh ids each call

    def test_the_time_budget_sets_the_truncated_flag(self):
        """`timeout` is per socket read and bounds no overall duration."""
        client = _client(budget_seconds=0)
        with patch.object(client, "_post", return_value=[{"idVisit": 1}]) as mock_post:
            visits = client.get_visits_since(datetime.datetime.now(datetime.UTC))
        assert client.truncated is True
        assert visits == []
        mock_post.assert_not_called()

    def test_a_clean_run_leaves_truncated_false(self):
        client = _client()
        with patch.object(client, "_post", return_value=[]):
            client.get_visits_since(datetime.datetime.now(datetime.UTC))
        assert client.truncated is False

    def test_the_page_cap_is_bounded(self):
        assert MAX_PAGES == 200
