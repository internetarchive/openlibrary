from unittest.mock import patch

import pytest
import web

from openlibrary.plugins.openlibrary import code


class TestBatchImportPendingView:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("", "/import/batch?status=needs_review"),
            ("?page=2&sort=added_time+asc", "/import/batch?status=needs_review&page=2&sort=added_time+asc"),
            ("?status=failed&page=3", "/import/batch?status=needs_review&page=3"),
        ],
    )
    def test_redirects_preserving_query(self, monkeypatch, query, expected):
        for name, value in {"path": "/import/batch/pending", "home": "", "query": query, "headers": [], "status": None}.items():
            monkeypatch.setattr(web.ctx, name, value, raising=False)
        with pytest.raises(web.Redirect):
            code.BatchImportPendingView().GET()
        assert web.ctx.status.startswith("301")
        assert dict(web.ctx.headers)["Location"] == expected


class TestBatchImportList:
    def _get(self, **params):
        with (
            patch("web.input", side_effect=lambda **defaults: web.storage({**defaults, **params})),
            patch.object(code.Batch, "list_summaries", return_value=(25, [])) as list_summaries,
            patch.object(code, "render_template") as render,
            patch.object(code, "_require_admin"),
        ):
            code.BatchImportList().GET()
        return list_summaries.call_args.kwargs, render.call_args.kwargs

    def test_defaults_to_all_statuses_newest_first(self):
        query, rendered = self._get()
        assert query == {"status": None, "sort": "added_time", "order": "desc", "limit": 10, "offset": 0}
        assert rendered["total_pages"] == 3

    def test_passes_valid_params(self):
        query, rendered = self._get(status="needs_review", sort="batch_id asc", page="2", limit="5")
        assert query == {"status": "needs_review", "sort": "batch_id", "order": "asc", "limit": 5, "offset": 5}
        assert rendered["total_pages"] == 5

    def test_clamps_limit(self):
        assert self._get(limit="-4")[0]["limit"] == 1
        assert self._get(limit="100000")[0]["limit"] == code.BatchImportList.MAX_LIMIT

    @pytest.mark.parametrize(
        "params",
        [{"status": "nope"}, {"sort": "status asc"}, {"sort": "added_time"}, {"sort": "garbage"}, {"page": "x", "limit": "x"}],
    )
    def test_invalid_params_fall_back_to_defaults(self, params):
        query, _ = self._get(**params)
        assert query == {"status": None, "sort": "added_time", "order": "desc", "limit": 10, "offset": 0}
