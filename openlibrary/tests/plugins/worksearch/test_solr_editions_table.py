"""Tests for minimal Solr-backed edition table component and helper functions."""

from unittest.mock import MagicMock, patch

from openlibrary.plugins.worksearch.code import get_solr_editions_for_work, work_solr_editions_table
from openlibrary.plugins.worksearch.schemes.editions import EditionSearchScheme


class TestSolrEditionsTableHelper:
    """Unit tests for get_solr_editions_for_work."""

    @patch("openlibrary.plugins.worksearch.code.run_solr_query")
    def test_get_solr_editions_for_work_defaults(self, mock_run_solr):
        mock_run_solr.return_value = MagicMock(num_found=5, docs=[{"key": "/books/OL1M", "title": "Test Edition"}])

        res = get_solr_editions_for_work(work_key="/works/OL82536W")

        assert res.num_found == 5
        mock_run_solr.assert_called_once()
        args, kwargs = mock_run_solr.call_args

        assert isinstance(args[0], EditionSearchScheme)
        assert args[1] == {"q": "*:*"}
        assert kwargs["facet"] is False
        assert kwargs["offset"] == 0
        assert kwargs["rows"] == 20
        assert kwargs["request_label"] == "WORK_SOLR_EDITIONS_TABLE"
        assert ("fq", 'work_key:"OL82536W"') in kwargs["extra_params"]

    @patch("openlibrary.plugins.worksearch.code.run_solr_query")
    def test_get_solr_editions_for_work_pagination(self, mock_run_solr):
        mock_run_solr.return_value = MagicMock(num_found=42, docs=[])

        get_solr_editions_for_work(
            work_key="/works/OL12345W/",
            page=3,
            limit=10,
        )

        args, kwargs = mock_run_solr.call_args
        assert args[1] == {"q": "*:*"}
        assert kwargs["offset"] == 20
        assert kwargs["rows"] == 10
        assert ("fq", 'work_key:"OL12345W"') in kwargs["extra_params"]


class TestWorkSolrEditionsTableHandler:
    """Tests for the work_solr_editions_table page handler."""

    @patch("openlibrary.plugins.worksearch.code.render_template")
    @patch("openlibrary.plugins.worksearch.code.get_solr_editions_for_work")
    @patch("web.ctx")
    @patch("web.input")
    def test_solr_editions_table_route_handler(self, mock_input, mock_ctx, mock_get_solr, mock_render):
        mock_work = MagicMock(key="/works/OL82536W", type=MagicMock(key="/type/work"))
        mock_ctx.site.get.return_value = mock_work
        mock_input.return_value = MagicMock(page=None, limit=None)
        mock_solr_res = MagicMock(num_found=2, docs=[{"key": "/books/OL1M"}])
        mock_get_solr.return_value = mock_solr_res
        mock_render.return_value = "<html>rendered table</html>"

        handler = work_solr_editions_table()
        result = handler.GET("/works/OL82536W")

        assert result == "<html>rendered table</html>"
        mock_get_solr.assert_called_once_with(
            "/works/OL82536W",
            page=1,
            limit=20,
            request_label="WORK_SOLR_EDITIONS_TABLE",
        )
        mock_render.assert_called_once()
        render_args = mock_render.call_args[0]
        assert render_args[0] == "type/work/solr_editions_table"
        assert render_args[1] == mock_work
        assert render_args[2] == mock_solr_res
