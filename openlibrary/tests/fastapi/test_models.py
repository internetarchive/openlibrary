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
