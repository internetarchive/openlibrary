import web

from openlibrary.plugins.worksearch.code import (
    _prepare_solr_query_params,
    get_doc,
    process_facet,
)
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme


def test_process_facet():
    facets = [("false", 46), ("true", 2)]
    assert list(process_facet("has_fulltext", facets)) == [
        ("true", "yes", 2),
        ("false", "no", 46),
    ]


def test_get_doc():
    doc = get_doc(
        {
            "author_key": ["OL218224A"],
            "author_name": ["Alan Freedman"],
            "cover_edition_key": "OL1111795M",
            "edition_count": 14,
            "first_publish_year": 1981,
            "has_fulltext": True,
            "ia": ["computerglossary00free"],
            "key": "/works/OL1820355W",
            "lending_edition_s": "OL1111795M",
            "public_scan_b": False,
            "title": "The computer glossary",
            "ratings_average": None,
            "ratings_count": None,
            "want_to_read_count": None,
        }
    )
    assert doc == web.storage(
        {
            "key": "/works/OL1820355W",
            "title": "The computer glossary",
            "url": "/works/OL1820355W/The_computer_glossary",
            "edition_count": 14,
            "ia": ["computerglossary00free"],
            "collections": [],
            "has_fulltext": True,
            "public_scan": False,
            "lending_edition": "OL1111795M",
            "lending_identifier": None,
            "authors": [
                web.storage(
                    {
                        "key": "OL218224A",
                        "name": "Alan Freedman",
                        "url": "/authors/OL218224A/Alan_Freedman",
                        "birth_date": None,
                        "death_date": None,
                    }
                )
            ],
            "first_publish_year": 1981,
            "first_edition": None,
            "subtitle": None,
            "cover_edition_key": "OL1111795M",
            "languages": [],
            "id_project_gutenberg": [],
            "id_project_runeberg": [],
            "id_librivox": [],
            "id_standard_ebooks": [],
            "id_openstax": [],
            "id_cita_press": [],
            "id_wikisource": [],
            "editions": [],
            "ratings_average": None,
            "ratings_count": None,
            "want_to_read_count": None,
            "series": [],
        }
    )


def test_prepare_solr_query_params_first_publish_year_string():
    """Test to check that when we have a facet value as a string it is converted to a list properly"""
    scheme = WorkSearchScheme()
    param = {"first_publish_year": "1997"}
    params, fields = _prepare_solr_query_params(scheme, param)

    param2 = {"first_publish_year": ["1997"]}
    params2, fields2 = _prepare_solr_query_params(scheme, param2)
    assert params == params2
    assert fields == fields2
    # Check that the fq param for first_publish_year is correctly added
    fq_params = [p for p in params if p[0] == "fq"]
    assert ("fq", 'first_publish_year:"1997"') in fq_params
