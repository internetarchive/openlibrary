import web
from unittest.mock import MagicMock
from openlibrary.plugins.worksearch.code import (
    process_facet,
    get_doc,
)


def test_process_facet():
    facets = [('false', 46), ('true', 2)]
    assert list(process_facet('has_fulltext', facets)) == [
        ('true', 'yes', 2),
        ('false', 'no', 46),
    ]


def mock_site():
    site = MagicMock()

    # Set up the mock site with the necessary data
    # For example, if the get() method should return a mock work object:
    mock_work = MagicMock()
    mock_work.key = "/works/OL1820355W"
    mock_work.get_editions.return_value = [{}, {}]
    site.get.return_value = mock_work

    return site


def test_get_doc():
    # Temporarily replace web.ctx.site with the mock_site object
    original_site = web.ctx.site
    web.ctx.site = mock_site()

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
        }
    )

    # Restore the original web.ctx.site
    web.ctx.site = original_site

    assert doc == web.storage(
        {
            'key': '/works/OL1820355W',
            'title': 'The computer glossary',
            'url': '/works/OL1820355W/The_computer_glossary',
            'edition_count': 14,
            'ia': ['computerglossary00free'],
            'collections': set(),
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
                    }
                )
            ],
            'first_publish_year': 1981,
            'first_edition': None,
            'subtitle': None,
            'cover_edition_key': 'OL1111795M',
            'languages': [],
            'id_project_gutenberg': [],
            'id_librivox': [],
            'id_standard_ebooks': [],
            'id_openstax': [],
            'editions': [],
        }
    )
