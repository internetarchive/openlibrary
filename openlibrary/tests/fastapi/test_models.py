import pytest

from openlibrary.fastapi.models import SolrInternalsParams, parse_comma_separated_list


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
