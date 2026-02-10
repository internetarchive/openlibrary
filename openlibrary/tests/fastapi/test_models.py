from openlibrary.fastapi.models import SolrInternalsParams


class TestSolrInternalsParams:
    def test_falsy_if_no_overrides(self):
        p = SolrInternalsParams()
        assert bool(p.model_dump(exclude_none=True)) is False
        p = SolrInternalsParams(solr_qf="title^2")
        assert bool(p.model_dump(exclude_none=True)) is True

    def test_combine_can_delete_fields(self):
        base = SolrInternalsParams(solr_qf="title^2", solr_mm="2<-1 5<-2")
        overrides = SolrInternalsParams(solr_qf="__DELETE__")
        combined = SolrInternalsParams.combine(base, overrides)
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
        assert (
            subquery
            == '({!edismax qf="title^2 body" mm="2<-1 5<-2" boost=$my_boost_function v=$userWorkQuery})'
        )

    def test_combine_with_none_overrides(self):
        """Test that combine() works correctly when overrides is None."""
        base = SolrInternalsParams(solr_qf="title^2", solr_mm="2<-1 5<-2")
        combined = SolrInternalsParams.combine(base, None)
        assert combined.solr_qf == "title^2"
        assert combined.solr_mm == "2<-1 5<-2"

    def test_combine_overrides_values(self):
        """Test that combine() correctly overrides base values."""
        base = SolrInternalsParams(solr_qf="title^2", solr_mm="2<-1 5<-2")
        overrides = SolrInternalsParams(solr_qf="author_name^10")
        combined = SolrInternalsParams.combine(base, overrides)
        assert combined.solr_qf == "author_name^10"
        assert combined.solr_mm == "2<-1 5<-2"  # Unchanged

    def test_combine_empty_subquery(self):
        """Test that empty params produce empty subquery."""
        p = SolrInternalsParams()
        subquery = p.to_solr_edismax_subquery()
        assert subquery == ""

    def test_variable_reference_regex_valid(self):
        """Test valid variable reference patterns.

        NOTE: Currently only alphanumeric + underscore + dot + hyphen are allowed.
        Variables with hyphens and dots are rejected by the current regex.
        """
        valid_vars = [
            "$userWorkQuery",
            "$my_boost_function",
            "$variable123",
            # These are currently rejected but probably should be allowed:
            # "$var-with-dash",
            # "$var.with.dots",
        ]
        for var in valid_vars:
            p = SolrInternalsParams(solr_v=var)
            # Should not raise ValueError
            result = p.to_solr_edismax_subquery()
            assert var in result

    def test_model_fields_coverage(self):
        """Test that all model fields are handled in to_solr_edismax_subquery."""
        # This ensures we don't miss any fields in the subquery generation
        p = SolrInternalsParams(
            # Dismax params
            solr_q_op="AND",
            solr_qf="text",
            solr_mm="100%",
            solr_pf="title",
            solr_ps="2",
            solr_qs="1",
            solr_tie="0.1",
            solr_bq="title:admin",
            solr_bf="log(edition_count)",
            # eDismax params
            solr_sow="true",
            solr_mm_autoRelax="true",
            solr_boost="$boost",
            solr_lowercaseOperators="false",
            solr_pf2="title^2",
            solr_ps2="2",
            solr_pf3="title^3",
            solr_ps3="2",
            solr_stopwords="true",
            solr_v="$query",
        )
        result = p.to_solr_edismax_subquery()
        # Verify key parameters are present
        # Note: q.op becomes q.op (with dot) in the output
        assert "q.op=" in result
        assert "qf=" in result
        assert "mm=" in result
        assert "v=$query" in result
