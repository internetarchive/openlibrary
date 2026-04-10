"""Tests for the fastapi models module."""

from unittest.mock import MagicMock

import pytest
from fastapi import Request

from openlibrary.fastapi.models import SolrInternalsParams, parse_comma_separated_list, wrap_jsonp


class TestWrapJsonp:
    """Unit tests for the wrap_jsonp helper function."""

    def test_no_callback_returns_json(self):
        """When no callback param, should return plain JSON with application/json content-type."""
        mock_request = MagicMock(spec=Request)
        type(mock_request.query_params).get = MagicMock(return_value=None)

        response = wrap_jsonp(mock_request, {"key": "value"})

        assert response.media_type == "application/json"
        assert response.body == b'{"key": "value"}'

    def test_with_callback_returns_jsonp(self):
        """When callback param present, should wrap in callback with application/javascript."""
        mock_request = MagicMock(spec=Request)
        type(mock_request.query_params).get = MagicMock(return_value="myCallback")

        response = wrap_jsonp(mock_request, {"key": "value"})

        assert response.media_type == "application/javascript"
        assert response.body == b'myCallback({"key": "value"});'

    def test_valid_callback_names(self):
        """Valid JavaScript identifier callbacks should be accepted."""
        valid_callbacks = ["jQuery123", "foo_bar", "_private", "callback", "foo.bar", "$", "a"]

        for callback in valid_callbacks:
            mock_request = MagicMock(spec=Request)
            type(mock_request.query_params).get = MagicMock(return_value=callback)

            response = wrap_jsonp(mock_request, {"test": 1})
            assert response.status_code == 200, f"Failed for callback: {callback}"

    def test_invalid_callback_names_rejected(self):
        """Invalid JavaScript identifier callbacks should be rejected."""
        invalid_callbacks = ["callback()", "callback;", "<script>", "a b c", "a-b", "1callback"]

        for callback in invalid_callbacks:
            mock_request = MagicMock(spec=Request)
            type(mock_request.query_params).get = MagicMock(return_value=callback)

            with pytest.raises(ValueError, match="Invalid callback parameter"):
                wrap_jsonp(mock_request, {"test": 1})

    def test_accepts_string_json(self):
        """Should accept pre-serialized JSON string in addition to dict."""
        mock_request = MagicMock(spec=Request)
        type(mock_request.query_params).get = MagicMock(return_value=None)

        response = wrap_jsonp(mock_request, '{"key": "value"}')

        assert response.media_type == "application/json"
        assert response.body == b'{"key": "value"}'

    def test_string_with_callback(self):
        """Pre-serialized JSON string should work with callback."""
        mock_request = MagicMock(spec=Request)
        type(mock_request.query_params).get = MagicMock(return_value="cb")

        response = wrap_jsonp(mock_request, '{"key": "value"}')

        assert response.media_type == "application/javascript"
        assert response.body == b'cb({"key": "value"});'


class TestParseCommaSeparatedList:
    """Tests for parse_comma_separated_list utility function.

    This function is used by FastAPI endpoints to parse comma-separated
    parameters from query strings into a clean list of values.
    """

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            (None, []),
            ("", []),
            ([], []),
        ],
    )
    def test_falsy_inputs_return_empty_list(self, input_val, expected):
        assert parse_comma_separated_list(input_val) == expected

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            ("key", ["key"]),
            (["key"], ["key"]),
        ],
    )
    def test_single_item(self, input_val, expected):
        assert parse_comma_separated_list(input_val) == expected

    def test_multiple_comma_separated_items(self):
        assert parse_comma_separated_list("key,title,author_name") == ["key", "title", "author_name"]

    def test_whitespace_trimming(self):
        assert parse_comma_separated_list(" key , title , author_name ") == ["key", "title", "author_name"]

    def test_empty_values_filtered(self):
        assert parse_comma_separated_list("key,,title") == ["key", "title"]

    def test_list_with_comma_separated_strings(self):
        assert parse_comma_separated_list(["key", "title,author_name"]) == ["key", "title", "author_name"]

    def test_list_with_whitespace_and_empty_strings(self):
        assert parse_comma_separated_list([" key ", "", " title "]) == ["key", "title"]

    def test_real_world_complex_case(self):
        assert parse_comma_separated_list("key,title,subtitle,author_name,author_key,cover_i,cover_edition_key") == [
            "key",
            "title",
            "subtitle",
            "author_name",
            "author_key",
            "cover_i",
            "cover_edition_key",
        ]


class TestSolrInternalsParams:
    def test_falsy_if_no_overrides(self):
        p = SolrInternalsParams()
        assert bool(p.model_dump(exclude_none=True)) is False
        p = SolrInternalsParams(solr_qf="title^2")
        assert bool(p.model_dump(exclude_none=True)) is True

    def test_override_can_delete_fields(self):
        base = SolrInternalsParams(solr_qf="title^2", solr_mm="2<-1 5<-2")
        overrides = SolrInternalsParams(solr_qf="__DELETE__")
        combined = SolrInternalsParams.override(base, overrides)
        assert combined.solr_qf is None
        assert combined.solr_mm == "2<-1 5<-2"

    def test_to_solr_edismax_subquery(self):
        p = SolrInternalsParams(
            solr_qf="title^2 body",
            solr_mm="2<-1 5<-2",
            solr_boost="$my_boost_function",
            solr_v="$userWorkQuery",
        )
        subquery = p.to_solr_edismax_subquery()
        assert subquery == '({!edismax qf="title^2 body" mm="2<-1 5<-2" boost=$my_boost_function v=$userWorkQuery})'
