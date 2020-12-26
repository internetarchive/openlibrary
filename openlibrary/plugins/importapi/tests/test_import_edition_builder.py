import pytest
from openlibrary.plugins.importapi.import_edition_builder import import_edition_builder 

import_examples = [
    {'edition_name': u'3rd ed.', 'pagination': u'xii, 444 p.', 'title': u'A course of pure mathematics', 'publishers': [u'At the University Press'], 'number_of_pages': 444, 'languages': ['eng'], 'publish_date': '1921', 'location': [u'GLAD'], 'authors': [{'birth_date': u'1877', 'personal_name': u'Hardy, G. H.', 'death_date': u'1947', 'name': u'Hardy, G. H.', 'entity_type': 'person'}], 'by_statement': u'by G.H. Hardy', 'publish_places': [u'Cambridge'], 'publish_country': 'enk'},
    {'publishers': [u'Ace Books'], 'pagination': u'271 p. ;', 'title': u'Neuromancer', 'lccn': [u'91174394'], 'notes': u'Hugo award book, 1985; Nebula award ; Philip K. Dick award', 'number_of_pages': 271, 'isbn_13': [u'9780441569595'], 'languages': ['eng'], 'dewey_decimal_class': [u'813/.54'], 'lc_classifications': [u'PS3557.I2264 N48 1984', u'PR9199.3.G53 N49 1984'], 'publish_date': '1984', 'publish_country': 'nyu', 'authors': [{'birth_date': u'1948', 'personal_name': u'Gibson, William', 'name': u'Gibson, William', 'entity_type': 'person'}], 'by_statement': u'William Gibson', 'oclc_numbers': ['24379880'], 'publish_places': [u'New York'], 'isbn_10': [u'0441569595']},
    {'publishers': [u'Grosset & Dunlap'], 'pagination': u'156 p.', 'title': u'Great trains of all time', 'lccn': [u'62051844'], 'number_of_pages': 156, 'languages': ['eng'], 'dewey_decimal_class': [u'625.2'], 'lc_classifications': [u'TF147 .H8'], 'publish_date': '1962', 'publish_country': 'nyu', 'authors': [{'birth_date': u'1894', 'personal_name': u'Hubbard, Freeman H.', 'name': u'Hubbard, Freeman H.', 'entity_type': 'person'}], 'by_statement': u'Illustrated by Herb Mott', 'oclc_numbers': [u'1413013'], 'publish_places': [u'New York']},
]

@pytest.mark.parametrize('data', import_examples)
def test_import_edition_builder_JSON(data):
    edition = import_edition_builder(init_dict=data)
    assert isinstance(edition, import_edition_builder)
    # JSON with the fields above is NOT altered by import_edition_builder
    assert edition.get_dict() == data
