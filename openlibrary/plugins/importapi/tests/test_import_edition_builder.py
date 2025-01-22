import pytest

from openlibrary.plugins.importapi.import_edition_builder import import_edition_builder

import_examples = [
    {
        'edition_name': '3rd ed.',
        'pagination': 'xii, 444 p.',
        'title': 'A course of pure mathematics',
        'publishers': ['At the University Press'],
        'number_of_pages': 444,
        'languages': ['eng'],
        'publish_date': '1921',
        'location': ['GLAD'],
        'authors': [
            {
                'birth_date': '1877',
                'personal_name': 'Hardy, G. H.',
                'death_date': '1947',
                'name': 'Hardy, G. H.',
                'entity_type': 'person',
            }
        ],
        'by_statement': 'by G.H. Hardy',
        'publish_places': ['Cambridge'],
        'publish_country': 'enk',
        'source_records': ['partner:book1'],
    },
    {
        'publishers': ['Ace Books'],
        'pagination': '271 p. ;',
        'title': 'Neuromancer',
        'lccn': ['91174394'],
        'notes': 'Hugo award book, 1985; Nebula award ; Philip K. Dick award',
        'number_of_pages': 271,
        'isbn_13': ['9780441569595'],
        'languages': ['eng'],
        'dewey_decimal_class': ['813/.54'],
        'lc_classifications': ['PS3557.I2264 N48 1984', 'PR9199.3.G53 N49 1984'],
        'publish_date': '1984',
        'publish_country': 'nyu',
        'authors': [
            {
                'birth_date': '1948',
                'personal_name': 'Gibson, William',
                'name': 'Gibson, William',
                'entity_type': 'person',
            }
        ],
        'by_statement': 'William Gibson',
        'oclc_numbers': ['24379880'],
        'publish_places': ['New York'],
        'isbn_10': ['0441569595'],
        'source_records': ['partner:book2'],
    },
    {
        'publishers': ['Grosset & Dunlap'],
        'pagination': '156 p.',
        'title': 'Great trains of all time',
        'lccn': ['62051844'],
        'number_of_pages': 156,
        'languages': ['eng'],
        'dewey_decimal_class': ['625.2'],
        'lc_classifications': ['TF147 .H8'],
        'publish_date': '1962',
        'publish_country': 'nyu',
        'authors': [
            {
                'birth_date': '1894',
                'personal_name': 'Hubbard, Freeman H.',
                'name': 'Hubbard, Freeman H.',
                'entity_type': 'person',
            }
        ],
        'by_statement': 'Illustrated by Herb Mott',
        'oclc_numbers': ['1413013'],
        'publish_places': ['New York'],
        'source_records': ['partner:book3'],
    },
]


@pytest.mark.parametrize('data', import_examples)
def test_import_edition_builder_JSON(data):
    edition = import_edition_builder(init_dict=data)
    assert isinstance(edition, import_edition_builder)
    # JSON with the fields above is NOT altered by import_edition_builder
    assert edition.get_dict() == data
