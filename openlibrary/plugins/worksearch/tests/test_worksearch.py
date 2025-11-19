import web

from openlibrary.mocks import mock_infobase
from openlibrary.plugins.worksearch.code import (
    get_doc,
    process_facet,
)


def test_process_facet():
    facets = [('false', 46), ('true', 2)]
    assert list(process_facet('has_fulltext', facets)) == [
        ('true', 'yes', 2),
        ('false', 'no', 46),
    ]


def test_get_doc():
    doc = get_doc(
        {
            'author_key': ['OL218224A'],
            'author_name': ['Alan Freedman'],
            'cover_edition_key': 'OL1111795M',
            'edition_count': 14,
            'first_publish_year': 1981,
            'has_fulltext': True,
            'ia': ['computerglossary00free'],
            'key': '/works/OL1820355W',
            'lending_edition_s': 'OL1111795M',
            'public_scan_b': False,
            'title': 'The computer glossary',
            'ratings_average': None,
            'ratings_count': None,
            'want_to_read_count': None,
        }
    )
    assert doc == web.storage(
        {
            'key': '/works/OL1820355W',
            'title': 'The computer glossary',
            'url': '/works/OL1820355W/The_computer_glossary',
            'edition_count': 14,
            'ia': ['computerglossary00free'],
            'collections': [],
            'has_fulltext': True,
            'public_scan': False,
            'lending_edition': 'OL1111795M',
            'lending_identifier': None,
            'authors': [
                web.storage(
                    {
                        'key': 'OL218224A',
                        'name': 'Alan Freedman',
                        'url': '/authors/OL218224A/Alan_Freedman',
                        'birth_date': None,
                        'death_date': None,
                    }
                )
            ],
            'first_publish_year': 1981,
            'first_edition': None,
            'subtitle': None,
            'cover_edition_key': 'OL1111795M',
            'languages': [],
            'id_project_gutenberg': [],
            'id_project_runeberg': [],
            'id_librivox': [],
            'id_standard_ebooks': [],
            'id_openstax': [],
            'id_cita_press': [],
            'id_wikisource': [],
            'editions': [],
            'ratings_average': None,
            'ratings_count': None,
            'want_to_read_count': None,
        }
    )


def test_rewrite_list_query(mock_site: mock_infobase.MockSite):
    from openlibrary.plugins.worksearch.code import rewrite_list_query

    mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}})
    mock_site.save({"key": "/works/OL2W", "type": {"key": "/type/work"}})
    mock_site.save(
        {
            "key": "/lists/OL123L",
            "type": {"key": "/type/list"},
            "seeds": [
                {"key": "/works/OL1W"},
                {"key": "/works/OL2W"},
            ],
        }
    )
    mock_site.save(
        {
            "key": "/lists/OL456L",
            "type": {"key": "/type/list"},
            "seeds": [
                {"key": "/works/OL2W"},
            ],
        }
    )
    mock_site.save(
        {
            "key": "/people/foo/lists/OL999L",
            "type": {"key": "/type/list"},
            "seeds": [
                {"key": "/authors/OL1A"},
            ],
        }
    )

    # Normal case
    query = 'list_key:/lists/OL123L subject:"Science Fiction"'
    rewritten_query = rewrite_list_query(query)
    assert (
        rewritten_query == 'key:(/works/OL1W OR /works/OL2W) subject:"Science Fiction"'
    )

    query = 'query without list_key'
    rewritten_query = rewrite_list_query(query)
    assert rewritten_query == query

    # Legacy: query begins with list key and no works in list
    query = '/people/foo/lists/OL999L AND subject:"Fantasy"'
    rewritten_query = rewrite_list_query(query)
    assert rewritten_query == '-key:* AND subject:"Fantasy"'  # List does not exist

    # Multiple list keys
    query = 'list_key:/lists/OL123L AND list_key:/lists/OL456L'
    rewritten_query = rewrite_list_query(query)
    assert rewritten_query == 'key:(/works/OL1W OR /works/OL2W) AND key:(/works/OL2W)'
